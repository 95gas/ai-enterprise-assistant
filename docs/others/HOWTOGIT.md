# Git Branching Strategy

This repository follows a structured Git branching strategy to ensure smooth development, testing, and production deployment. The strategy is designed to maintain stability in production while enabling efficient collaboration among developers.

## Branch Structure

### 1. Main Branches
- **`main` (or `prod`)** → Stable, production-ready code. Only tested and approved changes are merged here.
- **`dev`** → Active development branch. All feature branches should be merged here before release.

### 2. Supporting Branches
- **Feature branches (`feature/<feature-name>`)** → Created from `dev`, used for new features or major changes.
- **Bugfix branches (`bugfix/<bug-name>`)** → Created from `dev`, used for fixing non-production bugs.
- **Hotfix branches (`hotfix/<fix-name>`)** → Created from `main`, used for urgent production bug fixes.
- **Release branches (`release/<version>`)** → Created from `dev` when preparing a new release, allowing final testing and minor tweaks before merging into `main`.

## Workflow

### 1. Development
- Create a new feature or bugfix branch from `dev`:
  ```sh
  git checkout -b feature/new-feature dev
  ```
- Develop your feature, commit, and push:
  ```sh
  git commit -m "New feature implementation"
  git push origin feature/new-feature
  ```
- Create a **pull request (PR)** to merge your branch into `dev`.

### 2. Testing and Release Preparation
- Once features are merged into `dev`, automated tests and manual QA should be performed.
- When ready for a release, create a release branch:
  ```sh
  git checkout -b release/v1.0 dev
  ```

### 3. Production Deployment
- After final testing, merge the `release/<version>` branch into `main`:
  ```sh
  git checkout main
  git merge release/v1.0
  git tag v1.0.0
  git push origin main --tags
  ```
- Merge `main` back into `dev` to keep everything in sync:
  ```sh
  git checkout dev
  git merge main
  git push origin dev
  ```

### 4. Hotfixes for Production
- If a critical issue arises in production, create a hotfix branch from `main`:
  ```sh
  git checkout -b hotfix/urgent-fix main
  ```
- Fix the issue, commit, and push:
  ```sh
  git commit -m "Critical production fix"
  git push origin hotfix/urgent-fix
  ```
- Merge the hotfix back into `main` and `dev`:
  ```sh
  git checkout main
  git merge hotfix/urgent-fix
  git push origin main
  
  git checkout dev
  git merge main
  git push origin dev
  ```

## Best Practices
- **Use Pull Requests (PRs) for merging.**
- **Enforce code reviews** before merging changes.
- **Automate testing** using CI/CD tools.
- **Protect `main` and `dev` branches** by restricting direct commits.
- **Use semantic versioning** for release tags (e.g., `v1.0.0`).

This structure ensures a balance between development agility and production stability. Happy coding! 🚀

