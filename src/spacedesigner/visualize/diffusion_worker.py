"""Stable Diffusion 1.5 inpaint worker. Run with .venv-train so the API stays on CPU torch.

This process loads one diffusion pipeline, writes one PNG, and exits.
It does not download weights: from_pretrained uses local_files_only.
It does not import diffusers until main() runs.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Command-line paths.
import argparse

# Garbage collection before the process exits.
import gc

# Result is one JSON line.
import json

# Exit code.
import sys

# Pillow reads the maps the parent rendered.
from PIL import Image

# SD 1.5 inpainting checkpoint. Not SDXL.
SD_MODEL = "runwayml/stable-diffusion-inpainting"

# Depth ControlNet trained for SD 1.5.
CONTROL_MODEL = "lllyasviel/control_v11f1p_sd15_depth"

# Steps kept small so one image can finish on an 8 GB GPU.
STEPS = 20


# Load, inpaint, print JSON, and free the GPU.
def main() -> int:
    """Return 0 after one JSON line. A missing weight file is not_run, not a download."""
    # Arguments are file paths plus the prompt and seed.
    parser = argparse.ArgumentParser(description=__doc__)
    # Base RGB render.
    parser.add_argument("--base", required=True)
    # White pixels may be edited.
    parser.add_argument("--mask", required=True)
    # Depth conditioning image.
    parser.add_argument("--depth", required=True)
    # Where to write the generated PNG.
    parser.add_argument("--out", required=True)
    # Prompt built from the changed categories.
    parser.add_argument("--prompt", required=True)
    # Attempt seed.
    parser.add_argument("--seed", type=int, required=True)
    # Parsed args.
    args = parser.parse_args()
    # Any failure becomes a JSON note. Nothing is downloaded to recover.
    try:
        # Run the pipeline.
        _generate(args)
    # Missing packages, missing weights, or an out-of-memory error.
    except Exception as exc:
        # One JSON line the parent reads.
        print(json.dumps({"status": "not_run", "note": f"{type(exc).__name__}: {exc}"}))
        # The parent treats this as not_run and keeps the design.
        return 0
    # Success already printed JSON.
    return 0


# The only function that imports diffusers and CUDA torch.
def _generate(args: argparse.Namespace) -> None:
    """Inpaint the mask under ControlNet depth and write the PNG."""
    # Unload the chat model before any GPU weight is loaded.
    from spacedesigner.perception.runner import unload_llm

    # Ask Ollama to drop qwen2.5:7b. A missing daemon is ignored.
    unload_llm()
    # Diffusers is optional until a download is approved.
    # CUDA torch lives in .venv-train.
    import torch
    from diffusers import ControlNetModel, StableDiffusionControlNetInpaintPipeline

    # CPU diffusion is not the 8 GB check and would not finish in the route timeout.
    if not torch.cuda.is_available():
        # Tell the parent.
        print(json.dumps({"status": "not_run", "note": "cuda unavailable for diffusion"}))
        # Stop before loading weights.
        return
    # Start the peak counter at zero.
    torch.cuda.reset_peak_memory_stats()
    # Depth ControlNet, local files only.
    controlnet = ControlNetModel.from_pretrained(
        CONTROL_MODEL,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
        local_files_only=True,
    )
    # SD 1.5 inpaint plus that ControlNet. fp16 safetensors only. No safety-checker weights.
    pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        SD_MODEL,
        controlnet=controlnet,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
        safety_checker=None,
        requires_safety_checker=False,
        local_files_only=True,
    )
    # Slice attention so the peak stays under 8 GB.
    pipe.enable_attention_slicing()
    # One GPU.
    pipe = pipe.to("cuda")
    # Base, mask, and depth.
    base = Image.open(args.base).convert("RGB")
    # Mask is single channel. White is the editable region.
    mask = Image.open(args.mask).convert("L")
    # ControlNet expects a 3-channel depth image.
    depth = Image.open(args.depth).convert("RGB")
    # Fixed generator for this attempt.
    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    # Inpaint. The parent composites unchanged pixels afterwards.
    image = pipe(
        prompt=args.prompt,
        negative_prompt="text, watermark, extra furniture, distorted geometry",
        image=base,
        mask_image=mask,
        control_image=depth,
        num_inference_steps=STEPS,
        guidance_scale=7.5,
        controlnet_conditioning_scale=0.8,
        generator=generator,
    ).images[0]
    # Write the PNG before freeing the pipeline.
    image.save(args.out, format="PNG")
    # Peak allocated bytes since the reset.
    peak = float(torch.cuda.max_memory_allocated() / 2**20)
    # Drop the pipeline so the process exit returns the memory.
    del pipe, controlnet, generator
    # Collect Python references.
    gc.collect()
    # Return cached blocks.
    torch.cuda.empty_cache()
    # One JSON line. The parent reads the last stdout line.
    print(
        json.dumps(
            {
                "status": "generated",
                "note": "sd1.5 inpaint with controlnet depth",
                "peak_vram_mib": round(peak, 1),
            }
        )
    )


# Run as a module.
if __name__ == "__main__":
    # Propagate the code.
    sys.exit(main())
