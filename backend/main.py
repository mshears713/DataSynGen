"""
Measurement Dataset Foundry v0 — FastAPI Backend
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import config as config_router
from app.api import exports as exports_router
from app.api import health as health_router
from app.api import metrics as metrics_router
from app.api import runs as runs_router
from app.api import samples as samples_router
from app.core.exceptions import AppError, app_error_handler
from app.core.logging_config import configure_logging, get_logger
from app.core.settings import get_settings
from app.export.exporter import Exporter
from app.metrics.tracker import MetricsTracker
from app.pipeline.executor import PipelineExecutor
from app.pipeline.runner import PipelineRunner
from app.pipeline.spec_generator import SpecGenerator
from app.pipeline.stages import (
    GenerationStage,
    SchemaValidationStage,
    SemanticValidationStage,
)
from app.pipeline.text_generator import TextGenerator
from app.services.mock_llm import MockLLMService
from app.services.tokenrouter import TokenRouterService
from app.storage.config_store import ConfigStore
from app.storage.export_store import ExportStore
from app.storage.paths import ensure_storage_dirs
from app.storage.run_store import RunStore
from app.storage.sample_store import SampleStore
from app.validation.schema_validator import SchemaValidator
from app.validation.semantic_validator import SemanticValidator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = Path(__file__).parent / data_dir
    data_dir = data_dir.resolve()

    ensure_storage_dirs(data_dir)

    # Config
    config_store = ConfigStore(data_dir)
    try:
        config = config_store.load()
        logger.info(f"Config loaded from {config_store._config_path}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

    # Storage
    run_store = RunStore(data_dir)
    sample_store = SampleStore(data_dir)
    export_store = ExportStore(data_dir)

    # Recover any runs left in 'running' state from previous crash
    recovered = run_store.recover_stale_running_runs()
    if recovered:
        logger.warning(f"Recovered {len(recovered)} stale running runs: {recovered}")

    # LLM service
    if settings.mock_llm:
        logger.info("Using MockLLMService (MOCK_LLM=true)")
        llm_service = MockLLMService()
    else:
        logger.info(f"Using TokenRouterService at {settings.tokenrouter_base_url}")
        llm_service = TokenRouterService(
            base_url=settings.tokenrouter_base_url,
            api_key=settings.tokenrouter_api_key,
            config=config,
        )

    # Validators
    schema_validator = SchemaValidator(config)
    semantic_validator = SemanticValidator(llm_service, config)

    # Pipeline
    spec_generator = SpecGenerator(config)
    text_generator = TextGenerator(llm_service, config)

    stages = [
        GenerationStage(text_generator),
        SchemaValidationStage(schema_validator),
        SemanticValidationStage(semantic_validator),
    ]
    executor = PipelineExecutor(
        stages=stages,
        max_retries=config.generation.max_retries_on_empty,
    )
    pipeline_runner = PipelineRunner(
        executor=executor,
        spec_generator=spec_generator,
        run_store=run_store,
        sample_store=sample_store,
    )

    # Metrics + Export
    metrics_tracker = MetricsTracker(run_store, sample_store, data_dir)
    exporter = Exporter(sample_store, export_store, data_dir)

    # Attach to app state
    app.state.settings = settings
    app.state.data_dir = data_dir
    app.state.config_store = config_store
    app.state.run_store = run_store
    app.state.sample_store = sample_store
    app.state.export_store = export_store
    app.state.llm_service = llm_service
    app.state.pipeline_runner = pipeline_runner
    app.state.metrics_tracker = metrics_tracker
    app.state.exporter = exporter

    logger.info("Measurement Dataset Foundry backend started")
    yield

    logger.info("Measurement Dataset Foundry backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Measurement Dataset Foundry API",
        description="Backend API for synthetic measurement dataset generation",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(AppError, app_error_handler)

    # Routers
    app.include_router(health_router.router)
    app.include_router(config_router.router)
    app.include_router(runs_router.router)
    app.include_router(samples_router.router)
    app.include_router(metrics_router.router)
    app.include_router(exports_router.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
