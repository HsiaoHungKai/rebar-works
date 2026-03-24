---
name: sam3-inference
description: Run or modify SAM3 image inference on TWCC CCS using the bundled Python and shell CLIs in this folder. Use when Codex needs to segment an image with Hugging Face facebook/sam3 from either a text prompt or point prompts, especially when the task includes provisioning or reusing TWCC CCS resources through twccli, uploading inputs, running remote inference, and downloading artifacts.
---

# SAM3 Inference

Use this folder as the source of truth for single-image SAM3 inference on TWCC.

## Entry Points

- Use `infer.py` for inference logic.
- Use `run_twcc_inference.sh` for end-to-end TWCC CCS execution.
- Use `requirements.txt` for Python runtime dependencies.

## Workflow

1. Validate whether the request is local inference, TWCC remote inference, or a code change to one of the scripts.
2. For local inference, prefer `infer.py`.
3. For TWCC execution, prefer `run_twcc_inference.sh` and keep the existing `twccli`-driven CCS workflow unless the user asks for a different runtime.
4. Preserve the current prompt interface:
   - `--prompt-type text --text "..."`
   - `--prompt-type points --points "x,y,label;x,y,label;..."`
5. Preserve the default output contract unless the user asks to change it:
   - `mask.png`
   - `overlay.png`
   - `result.json`

## Prompt Modes

- Use `Sam3Model` with `Sam3Processor` for text-prompt segmentation.
- Use `Sam3TrackerModel` with `Sam3TrackerProcessor` for point-prompt segmentation.
- Treat point labels as SAM3 prompt labels:
  - `1` means positive
  - `0` means negative

## TWCC Notes

- Verify `twccli` availability and active project context before mutating TWCC resources.
- Keep CCS as the default runtime target.
- Keep the default image-selection behavior that discovers a PyTorch CCS image at runtime unless the user overrides it.
- Keep created CCS resources on failure for debugging; clean them up on success unless `--keep-resource` is set.

## Modification Guidance

- Keep the scripts executable.
- Keep CLI help text aligned with the implemented flags.
- When changing the shell script, prefer parsing `twccli` output in a way that matches the installed local CLI behavior.
- When changing the Python script, keep dependency imports lazy enough that `--help` works before installing runtime packages.
