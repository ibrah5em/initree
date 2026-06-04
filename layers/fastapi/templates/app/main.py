from fastapi import FastAPI

app = FastAPI(title="${project.name}")


@app.get("${app.healthcheck_path}")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "${project.slug}"}
