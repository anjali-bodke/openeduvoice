# Nvidia CUDA Installation Guide

This installation guide will enable the project to use Nvidia GPU and CUDA. This guide aims towards **Windows-11** users.

### Prerequisites 
- Ensure you have a **Nvidia RTX GPU** (Nvidia RTX 20XX - 50XX)

## 1. Get the GPU version.
- Open your Task Manager (cntr+shift+esc). Once task manager is opened click on performance of left side.
- Once in the performa tab, among the multiple hardware options; Click on the GPU (There may be multiple GPU based on PC configuration). 
- Note the name and series of the GPU.

## 2. Install the GPU drivers.
- Please visit [Nvidia GeForce Drivers](https://www.nvidia.com/en-us/geforce/drivers/).
- Choose the GPU series and download the drivers.
- After downloading, Install the drivers and check if the installation is succesful by searching Nvidia Control Panel.
- After checking Nvidia Control Panel, Open CMD as administrator and type **nvidia-smi**.
- You should be able to see a description about your GPU and a CUDA version.

## 3. Install Nvidia CUDA toolkit.
- After successful installation of drivers and ensuring the command **nvidia-smi** works and displays right information in command prompt, We can now move forward and download CUDA toolkit.
- [Nvidia Cuda Toolkit](https://developer.nvidia.com/cuda-downloads) This will take you to CUDA Toolkit website.
- Download the appropriate drivers based on your OS (Windows).
- make sure you choose exe(local) in the end.

# After driver + toolkit, **run install_OpenEduVoice.bat**. The installer will set up the required Python CUDA runtime packages.

# Finally after all the steps have been followed you can now use the Nvidia GPU with the help of CUDA toolkit for he software.
