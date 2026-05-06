"""Prompted predictor init and label-watcher loop."""

import asyncio
import logging
import multiprocessing
import os
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from user_models.prompted import PromptedPredictor
from user_models.data_manager import DataManager

logger = logging.getLogger(__name__)

_STATE_SUBDIR = ".prompted_predictor_state"
_STATE_FILES = ("retriever.json.gz", "state.json")
_INDEX_PROCESS_NICE = int(os.getenv("TADA_PROMPTED_INDEX_NICE", "15"))


def _state_dir(config) -> Path:
    return Path(config.log_dir) / _STATE_SUBDIR


def _state_dir_for_log_dir(log_dir: str) -> Path:
    return Path(log_dir) / _STATE_SUBDIR


def _install_state_files(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in _STATE_FILES:
        src = src_dir / name
        if src.exists():
            os.replace(src, dst_dir / name)


def _build_prompted_state_process(
    log_dir: str,
    model: str,
    retriever_checkpoint: str,
    output_state_dir: str,
    nice_increment: int,
) -> None:
    """Build the prompted retriever checkpoint outside the server process."""
    try:
        if nice_increment:
            try:
                os.nice(nice_increment)
            except OSError:
                pass

        dm = DataManager(log_dir=log_dir)
        dm._load_existing()

        predictor = PromptedPredictor(
            data_manager=dm,
            model=model,
            log_dir=log_dir,
            retriever_checkpoint=retriever_checkpoint or None,
        )
        if not retriever_checkpoint:
            predictor.load_state(_state_dir_for_log_dir(log_dir))
        predictor.index_context()
        predictor.save_state(output_state_dir)
    except BaseException:
        out = Path(output_state_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "error.txt").write_text(traceback.format_exc())
        raise


async def init_predictor(state, config, loop):
    state_dir = _state_dir(config)

    def _init():
        predictor = PromptedPredictor(
            data_manager=state.model.data_manager,
            model=config.prompted_model,
            api_key=config.resolve_api_key("default_llm_api_key"),
            log_dir=config.log_dir,
            # Honor explicit checkpoint when set; otherwise the auto-state path below
            # restores both the retriever and caption bookkeeping.
            retriever_checkpoint=config.retriever_checkpoint,
        )
        if not config.retriever_checkpoint:
            predictor.load_state(state_dir)
        return predictor

    state.model.predictor = await loop.run_in_executor(None, _init)
    logger.info(f"Prompted predictor initialized (model={config.prompted_model})")


async def _run_initial_index_process(state, config):
    """Refresh prompted retriever state in a low-priority child process."""
    output_dir = Path(tempfile.mkdtemp(
        prefix=".prompted_predictor_state.build.",
        dir=config.log_dir,
    ))
    proc = None
    try:
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_build_prompted_state_process,
            args=(
                config.log_dir,
                config.prompted_model,
                config.retriever_checkpoint or "",
                str(output_dir),
                _INDEX_PROCESS_NICE,
            ),
            name="prompted-indexer",
        )
        t0 = time.perf_counter()
        proc.start()
        logger.info(
            "Prompted predictor indexing process started (pid=%s nice=+%d)",
            proc.pid,
            _INDEX_PROCESS_NICE,
        )
        await asyncio.get_running_loop().run_in_executor(None, proc.join)
        elapsed = time.perf_counter() - t0

        if proc.exitcode != 0:
            error_path = output_dir / "error.txt"
            error = error_path.read_text() if error_path.exists() else f"exit code {proc.exitcode}"
            logger.warning("Prompted predictor indexing process failed: %s", error)
            return

        predictor = state.model.predictor
        if predictor is None:
            return

        # The expensive indexing happened in the child. This hot-loads the
        # finished checkpoint so the running predictor sees the refreshed state.
        await asyncio.get_running_loop().run_in_executor(None, predictor.load_state, output_dir)
        _install_state_files(output_dir, _state_dir(config))
        logger.info("Prompted predictor indexing process finished in %.1fs", elapsed)
    except asyncio.CancelledError:
        if proc is not None and proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        raise
    except Exception:
        logger.warning("Prompted predictor indexing process failed", exc_info=True)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


async def run_label_watcher(state):
    """Watch for label updates, broadcast status, and persist predictor state."""
    data_manager = state.model.data_manager
    config = state.config
    logger.info("Prompted mode: watching for label updates")
    initial_index_task = asyncio.create_task(_run_initial_index_process(state, config))
    try:
        while True:
            try:
                await asyncio.wait_for(data_manager.wait_for_label(), timeout=5.0)
                screen = state.connectors.get("screen")
                await state.broadcast("status", {
                    "recording_active": screen is not None and not screen.paused,
                    "training_active": False,
                    "labels_processed": data_manager.labels_processed,
                })
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        initial_index_task.cancel()
        try:
            await initial_index_task
        except asyncio.CancelledError:
            pass
        logger.info("Prompted label watcher cancelled — saving predictor state")
        predictor = state.model.predictor
        if predictor is not None:
            # Run in executor so we don't block the event loop on a multi-second
            # gzip+json dump. The dev supervisor's SIGTERM→SIGKILL window is sized
            # large enough (see scripts/dev-supervisor.cjs) to let this finish.
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, predictor.save_state, _state_dir(config)
                )
            except Exception:
                logger.warning("Failed to save prompted predictor state", exc_info=True)
        raise
