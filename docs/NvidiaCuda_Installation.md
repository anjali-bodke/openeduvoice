# NVIDIA GPU setup (Windows)

An NVIDIA GPU is optional; CPU mode is available but can be significantly slower.

1. Open Task Manager with **Ctrl+Shift+Esc**, select **Performance**, and note the
   NVIDIA GPU model.
2. Install a compatible driver from [NVIDIA](https://www.nvidia.com/en-us/geforce/drivers/).
3. Open a new PowerShell window and run `nvidia-smi` to check the driver and GPU.
4. Run `scripts\install_OpenEduVoice.bat`. The installer detects NVIDIA and
   selects the CUDA PyTorch wheels. To explicitly select a mode, run
   `.\scripts\install_OpenEduVoice.bat cuda` or use `cpu`.

A separate CUDA toolkit is not normally required for the packaged PyTorch wheels.
The reported CUDA version in `nvidia-smi` reflects driver support; it does not
prove that PyTorch or faster-whisper can use the GPU. The installer checks
PyTorch and falls back to CPU if CUDA is unavailable. GPU compatibility also
depends on the driver, hardware, and the versions of the CUDA libraries.

If a previous virtual environment was installed for another mode, back it up or
remove it manually before switching modes. Review the installer log and test with
a small document. See the [runbook](RUNBOOK.md) for additional checks.
