from argparse import ArgumentParser
from dataclasses import fields, MISSING
from typing import get_type_hints, get_origin, get_args
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, Qwen3VLForConditionalGeneration, AutoProcessor
from peft import LoraConfig

PEFT_CONFIG = LoraConfig(
    lora_alpha=32,
    lora_dropout=0.05,
    r=8,
    bias="none",
    target_modules=["gate_proj", "up_proj", "down_proj"],
    task_type="CAUSAL_LM",
    use_rslora=True,
)


def add_dataclass_args_to_parser(parser: ArgumentParser, dataclass_type, prefix: str = ""):
    type_hints = get_type_hints(dataclass_type)
    for field in fields(dataclass_type):
        if not field.init:
            continue
        name = field.name
        field_type = type_hints.get(name, field.type)

        origin = get_origin(field_type)
        args = get_args(field_type)
        if args and any(a is type(None) for a in args):
            non_none = next((a for a in args if a is not type(None)), None)
            field_type = non_none
            origin = get_origin(field_type)
        # -----------------------------------------------------------------------

        # detect list[T]
        inner_type = None
        if origin is list or getattr(field_type, '__origin__', None) is list:
            inner_args = get_args(field_type)
            inner_type = inner_args[0] if inner_args else str

        opt = f"--{prefix}{name.replace('_', '-')}"
        is_required = (field.default is MISSING and field.default_factory is MISSING)
        if field.default is not MISSING:
            default = field.default
        elif field.default_factory is not MISSING:
            default = field.default_factory()
        else:
            default = None
        help_text = f"{name} (default: {default})"

        if field_type is bool:
            if default is True:
                parser.add_argument(opt, action="store_false", default=True, required=False, help=help_text)
            else:
                parser.add_argument(opt, action="store_true", default=False, required=False, help=help_text)
        elif origin is list or field_type is list:
            parser.add_argument(opt,
                                nargs='+',
                                type=inner_type or str,
                                default=(default if default is not None else None),
                                required=is_required,
                                help=help_text)
        elif field_type in (int, float, str):
            parser.add_argument(opt,
                                type=field_type,
                                default=default,
                                required=is_required,
                                help=help_text)
        else:
            parser.add_argument(opt,
                                type=str,
                                default=default,
                                required=is_required,
                                help=help_text)


def extract_dataclass_args(args, prefix="training_"):
    """
    Extract parsed args that start with prefix (use underscore form here, e.g. 'training_').
    Returns a dict keyed by the original dataclass field names (without prefix).
    """
    if prefix.endswith('-'):
        prefix = prefix.replace('-', '_')
    result = {}
    for key, value in vars(args).items():
        if key.startswith(prefix):
            result[key.replace(prefix, "")] = value
    return result


def load_processor(model_name: str):
    processor = AutoProcessor.from_pretrained(
        model_name,
        max_pixels=1024 * 600,
        padding_side="left"
    )
    processor.tokenizer.padding_side = "left"
    return processor


def load_model(model_name: str):
    if "Qwen2.5-VL" in model_name:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16
        )
    elif "Qwen3-VL" in model_name:
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16
        )
    return model
