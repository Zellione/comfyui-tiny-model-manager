# Project
ComfyUI custom-node to manage and download models, LORAs, workflows from CivitAI and huggingface.
Goal: Dashboard to manage Models/LORAs and custom nodes to insert them with their documented trigger words

## Tech Stack
### Frontend
- Angular 21.2 (zoneless, no Zone.js)

### Backend
- Python 3.13.12
- ComfyUI python_embedded can be found at ../../../python_embeded/
- pip need to be called with python.exe -m pip
- Persistence through SQLite files in a subfolder folder
- Huggingface.co API (consult documentation: https://huggingface.co/.well-known/openapi.md)
- CivitAI API (consult documentation: https://developer.civitai.com/site/reference/)

For further information you can Check the official documentation https://docs.comfy.org/custom-nodes/overview

## Workflow
- Commits and code comments always in english
- Claude never mentions it self as Coauthor or uses EOF in commit message