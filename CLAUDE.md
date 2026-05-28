# Project
ComfyUI custom-node to manage and download models, LORAs, workflows from CivitAI and huggingface.
Goal: Dashboard to manage Models/LORAs and custom nodes to insert them with their documented trigger words

## Tech Stack
### Frontend
- Angular 21.2 (zoneless, no Zone.js)

#### Build
ComfyUI serves the compiled output in `web/` (git-ignored). Any change to `frontend/` or `js/`
requires a rebuild before it takes effect. Run from the `frontend/` directory:

```
# once, or after changing package.json dependencies
npm install

# production build → outputs to ../web/  (default configuration is production)
npx ng build

# auto-rebuild during active development
npx ng build --watch --configuration development
```

The `js/` ComfyUI extension folder is copied into `web/` as a build asset — it is bundled by
the same `ng build` call and must not be deployed separately.

The Python backend (`py/`) needs no build step; changes take effect after restarting ComfyUI.

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

### Feature

If planning and working on a new feature already specified in @PRD.md the following steps have to be executed, if not already happened:

1. Change Branch to main
2. Fetch from origin and pull changes
3. Create git branch containing feature name in the format `F-12-very-short-name`
4. Enter plan mode and plan feature
5. Wait for approval of plan
6. If plan was approved implement plan
7. If there are no bugs reported: commit changes and push them to github (origin)
8. Open pull request

### Bug during feature development.

If working on a bug during feature development and it was alrady pushed and a pull request created:

1. Make sure to be on feature branch, if not checkout
2. Enter plan mode
3. Analyze the bug
4. Make a plan to fix the bug
5. Wait for approval of plan
6. If plan was approved implement plan.
7. If there are no bugs reported: commit changes and push them to github (origin)
8. Check if pull request updated