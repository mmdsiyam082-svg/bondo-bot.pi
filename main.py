import os
import sys
import uuid
import signal
import asyncio
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

PYTHON_BIN = sys.executable


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Python Hosting API",
    version="1.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Production-এ নির্দিষ্ট HopWeb domain দাও
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# RUNNING PROCESSES
# =========================================================

processes: Dict[str, asyncio.subprocess.Process] = {}


# =========================================================
# HELPERS
# =========================================================

def project_path(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def script_path(project_id: str) -> Path:
    return project_path(project_id) / "main.py"


def logs_path(project_id: str) -> Path:
    return project_path(project_id) / "logs.txt"


def is_running(project_id: str) -> bool:

    process = processes.get(project_id)

    if process is None:
        return False

    return process.returncode is None


def write_log(project_id: str, text: str):

    path = logs_path(project_id)

    with path.open(
        "a",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        f.write(text)

        if not text.endswith("\n"):
            f.write("\n")


def read_logs(project_id: str) -> str:

    path = logs_path(project_id)

    if not path.exists():
        return ""

    try:

        data = path.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        # Prevent huge response
        return data[-50000:]

    except Exception:
        return ""


# =========================================================
# PROCESS LOG READER
# =========================================================

async def capture_output(
    project_id: str,
    stream,
    prefix: str
):

    try:

        while True:

            line = await stream.readline()

            if not line:
                break

            text = line.decode(
                "utf-8",
                errors="replace"
            )

            write_log(
                project_id,
                f"{prefix} {text}"
            )

    except asyncio.CancelledError:
        pass

    except Exception as e:

        write_log(
            project_id,
            f"[LOG ERROR] {e}"
        )


# =========================================================
# PROCESS MONITOR
# =========================================================

async def monitor_process(
    project_id: str,
    process: asyncio.subprocess.Process
):

    stdout_task = asyncio.create_task(
        capture_output(
            project_id,
            process.stdout,
            "[OUT]"
        )
    )

    stderr_task = asyncio.create_task(
        capture_output(
            project_id,
            process.stderr,
            "[ERR]"
        )
    )

    try:

        return_code = await process.wait()

        await stdout_task
        await stderr_task

        write_log(
            project_id,
            f"\n[PROCESS EXITED] code={return_code}\n"
        )

    except Exception as e:

        write_log(
            project_id,
            f"\n[PROCESS ERROR] {e}\n"
        )

    finally:

        if processes.get(project_id) is process:
            processes.pop(project_id, None)


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
async def health():

    running = sum(
        1
        for pid in processes
        if is_running(pid)
    )

    return {
        "status": "online",
        "python": sys.version.split()[0],
        "running_projects": running
    }


# =========================================================
# UPLOAD
# =========================================================

@app.post("/api/projects/upload")
async def upload_project(
    file: UploadFile = File(...)
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file selected"
        )

    filename = Path(
        file.filename
    ).name

    if not filename.lower().endswith(".py"):

        raise HTTPException(
            status_code=400,
            detail="Only .py files are allowed"
        )

    project_id = uuid.uuid4().hex[:12]

    directory = project_path(
        project_id
    )

    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    target = script_path(
        project_id
    )

    try:

        content = await file.read()

        if len(content) > MAX_FILE_SIZE:

            raise HTTPException(
                status_code=413,
                detail="File is too large. Maximum 5 MB."
            )

        target.write_bytes(content)

        logs_path(
            project_id
        ).write_text(
            f"[SYSTEM] Project uploaded: {filename}\n",
            encoding="utf-8"
        )

        return {
            "success": True,
            "id": project_id,
            "name": filename,
            "status": "stopped",
            "message": "Project uploaded successfully."
        }

    except HTTPException:
        raise

    except Exception as e:

        if directory.exists():

            import shutil

            shutil.rmtree(
                directory,
                ignore_errors=True
            )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# LIST PROJECTS
# =========================================================

@app.get("/api/projects")
async def list_projects():

    result = []

    for directory in PROJECTS_DIR.iterdir():

        if not directory.is_dir():
            continue

        pid = directory.name

        script = script_path(pid)

        if not script.exists():
            continue

        status = (
            "running"
            if is_running(pid)
            else "stopped"
        )

        result.append(
            {
                "id": pid,
                "name": script.name,
                "status": status
            }
        )

    return result


# =========================================================
# RUN
# =========================================================

@app.post("/api/projects/{project_id}/run")
async def run_project(
    project_id: str
):

    script = script_path(
        project_id
    )

    if not script.exists():

        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    if is_running(project_id):

        return {
            "success": True,
            "message": "Project is already running."
        }

    write_log(
        project_id,
        "\n[SYSTEM] Starting Python project...\n"
    )

    try:

        process = await asyncio.create_subprocess_exec(

            PYTHON_BIN,

            "-u",

            str(script),

            cwd=str(
                project_path(project_id)
            ),

            stdin=asyncio.subprocess.DEVNULL,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE,

            start_new_session=True
        )

        processes[project_id] = process

        asyncio.create_task(
            monitor_process(
                project_id,
                process
            )
        )

        write_log(
            project_id,
            f"[SYSTEM] Started. PID={process.pid}\n"
        )

        return {
            "success": True,
            "message": f"Project started. PID={process.pid}",
            "pid": process.pid
        }

    except Exception as e:

        write_log(
            project_id,
            f"[SYSTEM] Start failed: {e}\n"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# STOP
# =========================================================

@app.post("/api/projects/{project_id}/stop")
async def stop_project(
    project_id: str
):

    process = processes.get(
        project_id
    )

    if process is None:

        return {
            "success": True,
            "message": "Project is not running."
        }

    if process.returncode is not None:

        processes.pop(
            project_id,
            None
        )

        return {
            "success": True,
            "message": "Project already stopped."
        }

    try:

        # Kill process group
        try:

            os.killpg(
                os.getpgid(process.pid),
                signal.SIGTERM
            )

        except Exception:

            process.terminate()

        try:

            await asyncio.wait_for(
                process.wait(),
                timeout=5
            )

        except asyncio.TimeoutError:

            try:

                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL
                )

            except Exception:

                process.kill()

            await process.wait()

        write_log(
            project_id,
            "\n[SYSTEM] Project stopped.\n"
        )

        processes.pop(
            project_id,
            None
        )

        return {
            "success": True,
            "message": "Project stopped successfully."
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# RESTART
# =========================================================

@app.post("/api/projects/{project_id}/restart")
async def restart_project(
    project_id: str
):

    process = processes.get(
        project_id
    )

    if process is not None:

        if process.returncode is None:

            try:

                try:

                    os.killpg(
                        os.getpgid(process.pid),
                        signal.SIGTERM
                    )

                except Exception:

                    process.terminate()

                try:

                    await asyncio.wait_for(
                        process.wait(),
                        timeout=5
                    )

                except asyncio.TimeoutError:

                    try:

                        os.killpg(
                            os.getpgid(process.pid),
                            signal.SIGKILL
                        )

                    except Exception:

                        process.kill()

                    await process.wait()

            except Exception:
                pass

        processes.pop(
            project_id,
            None
        )

    await asyncio.sleep(0.5)

    return await run_project(
        project_id
    )


# =========================================================
# LOGS
# =========================================================

@app.get("/api/projects/{project_id}/logs")
async def project_logs(
    project_id: str
):

    if not project_path(
        project_id
    ).exists():

        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    status = (
        "running"
        if is_running(project_id)
        else "stopped"
    )

    return {
        "id": project_id,
        "status": status,
        "logs": read_logs(project_id)
    }


# =========================================================
# DELETE
# =========================================================

@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str
):

    process = processes.get(
        project_id
    )

    if process is not None:

        if process.returncode is None:

            try:

                try:

                    os.killpg(
                        os.getpgid(process.pid),
                        signal.SIGTERM
                    )

                except Exception:

                    process.terminate()

                await asyncio.wait_for(
                    process.wait(),
                    timeout=5
                )

            except Exception:
                pass

        processes.pop(
            project_id,
            None
        )

    directory = project_path(
        project_id
    )

    if not directory.exists():

        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    import shutil

    shutil.rmtree(
        directory,
        ignore_errors=True
    )

    return {
        "success": True,
        "message": "Project deleted."
    }


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8000
            )
        )
    )