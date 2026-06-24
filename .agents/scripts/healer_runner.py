import os
import sys
import zipfile
import io
from pathlib import Path
import requests
from openai import OpenAI

# ==========================================
# 1. Environment & API Setup
# ==========================================
# These variables are automatically injected by the GitHub Actions environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
FAILED_RUN_ID = os.getenv("FAILED_RUN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# GitHub Repository name is usually formatted as "owner/repo" (e.g. "ok-karthik/enterprise-aws-platform-terragrunt")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")

if not GITHUB_TOKEN or not FAILED_RUN_ID or not GITHUB_REPOSITORY:
    print("❌ Error: Missing required GitHub Actions environment variables.")
    sys.exit(1)

if not GROQ_API_KEY:
    print("❌ Error: GROQ_API_KEY is not set.")
    sys.exit(1)

# Initialize OpenAI-compatible client targeting Groq
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# Resolve paths relative to this script
BASE_DIR = Path(__file__).parent.parent if "__file__" in locals() else Path(".")
CI_HEALER_PROMPT_PATH = BASE_DIR / "prompts" / "ci_healer.md"


# ==========================================
# 2. Fetch Failed Logs from GitHub API
# ==========================================
def download_failed_logs(run_id: str, repo: str, token: str) -> str:
    """
    Downloads the execution logs for a specific GitHub workflow run.
    GitHub returns this as a ZIP archive containing text log files for each job.
    """
    print(f"📥 Fetching logs for run ID: {run_id} in repo: {repo}...")
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.get(url, headers=headers, stream=True)
    if response.status_code != 200:
        print(f"❌ Failed to fetch logs. API Status: {response.status_code}")
        sys.exit(1)

    # Read the downloaded ZIP file in memory
    zip_file_bytes = io.BytesIO(response.content)
    log_contents = []

    with zipfile.ZipFile(zip_file_bytes, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            # Skip metadata files, focus on job log files (.txt)
            if file_info.filename.endswith(".txt") and not "/" in file_info.filename:
                with zip_ref.open(file_info.filename) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    # Keep only the last 300 lines of each log to stay within token limits
                    lines = content.splitlines()[-300:]
                    log_contents.append(f"=== Job Log: {file_info.filename} ===\n" + "\n".join(lines))

    return "\n\n".join(log_contents)


# ==========================================
# 3. Main Agent Loop
# ==========================================
def main():
    # 1. Download logs
    failed_logs = download_failed_logs(FAILED_RUN_ID, GITHUB_REPOSITORY, GITHUB_TOKEN)
    if not failed_logs.strip():
        print("⚠️ No log files found in the archive.")
        sys.exit(0)

    # 2. Load system prompt instructions
    if not CI_HEALER_PROMPT_PATH.exists():
        print(f"❌ System prompt file not found at: {CI_HEALER_PROMPT_PATH}")
        sys.exit(1)
    system_prompt = CI_HEALER_PROMPT_PATH.read_text().strip()

    print("\n🧠 [Healer Agent] Analyzing logs with Groq (llama-3.3-70b-versatile)...")

    # 3. Call Groq LLM
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"The pipeline crashed with these logs:\n\n{failed_logs}"}
        ],
        temperature=0.1
    )

    patch_code = response.choices[0].message.content.strip()

    print("\n🛡️ Generated Patch / Recommendation:")
    print("==========================================")
    print(patch_code)
    print("==========================================")

    # Write the output patch to a local file so the GHA workflow can apply it if needed
    with open("patch_proposal.diff", "w") as pf:
        pf.write(patch_code)
    print("💾 Saved patch proposal to patch_proposal.diff")

if __name__ == "__main__":
    main()
