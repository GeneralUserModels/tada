"""Inference polling loop: predicts next actions and evaluates against ground truth."""

import logging
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from powernap.longnap.trainer_utils import build_actions_block

try:
    import wandb
except ImportError:
    wandb = None

logger = logging.getLogger(__name__)


def inference_loop(predictor, inference_buffer, trainer, recorder,
                   past_len, future_len, processor, predict_interval,
                   reward_llm, overlay, walker, num_imgs_per_sample=0):

    executor = ThreadPoolExecutor(max_workers=8)
    pending_predictions = []  # (future, buffer_pos, seq)

    last_path = None
    prediction_count = 0
    prediction_seq = 0
    latest_completed_seq = 0
    eval_count = 0
    pending_evals = []
    buffer_trim_offset = 0  # total items trimmed from front of inference_buffer
    prediction_submitted = False  # single-shot: reset when overlay hides

    while recorder.running:
        # Pick up new checkpoint
        path = getattr(trainer, "latest_sampler_path", None)
        if path and path != last_path:
            predictor.model_path = path
            last_path = path
            print(f"[inference] using checkpoint: {path}")

        # Single-shot prediction: fire once when overlay becomes visible
        cur_buffer_len = buffer_trim_offset + len(inference_buffer)
        is_visible = overlay._visible if overlay else False

        if not is_visible:
            prediction_submitted = False  # reset so next show triggers a new prediction

        if (is_visible and not prediction_submitted and predictor.model_path
                and cur_buffer_len >= past_len):
            buffer_pos = cur_buffer_len
            prediction_seq += 1

            sampling_client = trainer.sampling_client
            buffer_snapshot = list(inference_buffer[-past_len:])

            future = executor.submit(
                predictor.predict_from_snapshot,
                buffer_snapshot, future_len,
                sampling_client=sampling_client,
                num_imgs_per_sample=num_imgs_per_sample,
            )
            prediction_submitted = True
            pending_predictions.append((future, buffer_pos, prediction_seq))
            print(f"[inference] submitted prediction seq {prediction_seq} (buffer={buffer_pos}, in-flight={len(pending_predictions)})")

        # collect completed predictions
        still_pending_preds = []
        for future, buf_pos, seq in pending_predictions:
            if future.done():
                try:
                    result = future.result()
                except Exception as e:
                    logger.warning(f"Prediction failed: {e}. Skipping.")
                    continue
                prediction_count += 1

                print(f"[inference] prediction #{prediction_count} (seq {seq}) complete:")
                print(f"  actions: {result['actions']}")

                actions_parsed = bool(re.search(r"<action>", result["actions"]))

                if not actions_parsed:
                    print(f"[inference] prediction #{prediction_count}: no <action> tags, reward=0")
                else:
                    # track for eval scoring
                    pending_evals.append((result, buf_pos, future_len))

                    # update overlay/walker only if this is newer than the last displayed
                    if seq > latest_completed_seq:
                        latest_completed_seq = seq
                        if overlay and not walker.active.is_set():
                            overlay.update(result["actions"])
                        walker.latest_prediction = {"actions": result["actions"], "seq": seq}

                if wandb and wandb.run is not None:
                    wandb.log({
                        "inference/predictions_total": prediction_count,
                        "inference/in_flight": len(still_pending_preds),
                    })
            else:
                still_pending_preds.append((future, buf_pos, seq))
        pending_predictions = still_pending_preds

        # Check pending evals
        still_pending = []
        for result, buf_pos, fl in pending_evals:
            logical_len = buffer_trim_offset + len(inference_buffer)
            start = buf_pos - buffer_trim_offset
            if logical_len >= buf_pos + fl and start >= 0:
                ground_truth = build_actions_block(inference_buffer[start:start + fl])
                try:
                    reward = predictor.score_prediction(result["actions"], ground_truth, reward_llm)
                except Exception as e:
                    logger.warning(f"Score prediction failed: {e}. Skipping eval.")
                    continue
                eval_count += 1

                print(f"[inference] eval #{eval_count}: reward={reward:.2f}")

                if wandb and wandb.run is not None:
                    wandb.log({
                        "inference/reward": reward,
                        "inference/evals_total": eval_count,
                    })
            elif start < 0:
                # Items were trimmed away, skip this eval
                pass
            else:
                still_pending.append((result, buf_pos, fl))
        pending_evals = still_pending

        # Trim old items from inference_buffer that are no longer needed
        all_pending_pos = (
            [bp for _, bp, _ in pending_predictions]
            + [bp for _, bp, _ in pending_evals]
        )
        if all_pending_pos:
            min_needed = min(all_pending_pos)
        else:
            min_needed = buffer_trim_offset + len(inference_buffer)
        safe_trim = max(0, min_needed - past_len - buffer_trim_offset)
        if safe_trim > 0:
            del inference_buffer[:safe_trim]
            buffer_trim_offset += safe_trim

        time.sleep(1)
