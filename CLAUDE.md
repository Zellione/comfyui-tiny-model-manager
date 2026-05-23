# Project
ComfyUI custom-node to manage and download models, LORAs, workflows from CivitAI and huggingface.
Goal: Dashboard to manage Models/LORAs and custom nodes to insert them with their documented trigger words

# Tech Stack
## Frontend
- Angular JS

## Backend
- Python
- ComfyUI python_embedded can be found at ../../../python_embedded
- pip need to be called with python.exe -m pip
- Persistence through SQLite files in a subfolder folder

For further information you can Check the official documentation https://docs.comfy.org/custom-nodes/overview

# Workflow
- Commits and code comments always in english

# Phases
## Phase 1
Create a skeleton folder structure and implement mendatory files according to documentation

## Phase 2
Create basic frontend UI and backend logic to download view and download models from huggingface and CivitAI using
their APIs.
Downloaded models should be put in the according model subfolders of ComfyUI.

## Phase 3
Model data like example images and videos should be downloaded on model download be stored in a configurable folder.
The model meta information like description, trigger words and so on should be stored in a sqlite file.
The installed models should be viewable in the frontend UI.