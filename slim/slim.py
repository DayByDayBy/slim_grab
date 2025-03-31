import requests
import sqlite3
import json
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    raise ValueError("GitHub token is missing")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

def create_db():
    conn = sqlite3.connect("fixed_issues.db")
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixed_issues (
            issue_url TEXT PRIMARY KEY,
            repo_name TEXT,
            pull_request_url TEXT,
            languages TEXT,
            before_code_url TEXT,
            after_code_url TEXT,
            affected_files TEXT
        )
    """)
    conn.commit()
    conn.close()

def make_request(url):
    """Helper function to handle rate limits and retries."""
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response
        elif response.status_code == 403 and "X-RateLimit-Reset" in response.headers:
            reset_time = int(response.headers["X-RateLimit-Reset"])
            sleep_time = max(0, reset_time - time.time())
            print(f"Rate limit exceeded. Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
        elif response.status_code in [502, 503, 504]:  # Temporary server errors
            print(f"Temporary error ({response.status_code}). Retrying in 5 seconds...")
            time.sleep(5)
        else:
            print(f"Request failed: {response.status_code}")
            return None

def get_mit_repos(query="stars:>100", per_page=100, pages=10):
    repos = []
    for page in range(1, pages + 1):
        url = f"https://api.github.com/search/repositories?q={query}+license:mit&sort=stars&order=desc&per_page={per_page}&page={page}"
        response = make_request(url)
        if response:
            data = response.json()
            repos.extend(data.get("items", []))
        else:
            print(f"Failed to fetch repositories (page {page})")
            return []
    return repos

def get_issues(repo_name):
    url = f"https://api.github.com/repos/{repo_name}/issues?state=closed&per_page=100"
    response = make_request(url)
    return response.json() if response else []

def get_pull_request_from_issue(repo_name, issue_number):
    url = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}/timeline?per_page=100"
    response = make_request(url)
    if response:
        timeline = response.json()
        for event in timeline:
            if event.get("event") == "cross-referenced" and "pull" in event.get("source", {}).get("issue", {}).get("html_url", ""):
                return event["source"]["issue"]["html_url"]
    return None

def get_languages(repo_name):
    url = f"https://api.github.com/repos/{repo_name}/languages"
    response = make_request(url)
    return json.dumps(list(response.json().keys())) if response else "[]"

def get_code_before_after(pr_url):
    if not pr_url:
        return None, None
    pr_api_url = pr_url.replace("github.com", "api.github.com/repos").replace("/pull/", "/pulls/")
    response = make_request(pr_api_url)
    if not response:
        return None, None
    pr_data = response.json()
    base_sha = pr_data.get("base", {}).get("sha")
    head_sha = pr_data.get("head", {}).get("sha")
    repo_name = pr_data.get("base", {}).get("repo", {}).get("full_name")
    if not base_sha or not head_sha or not repo_name:
        return None, None
    return (f"https://github.com/{repo_name}/commit/{base_sha}", f"https://github.com/{repo_name}/commit/{head_sha}")

def get_affected_files(pr_url):
    if not pr_url:
        return "[]"
    pr_api_url = pr_url.replace("github.com", "api.github.com/repos") + "/files"
    response = make_request(pr_api_url)
    return json.dumps([file["filename"] for file in response.json()]) if response else "[]"

def populate_db(repos):
    conn = sqlite3.connect("fixed_issues.db")
    cursor = conn.cursor()
    for repo in repos:
        repo_name = repo["full_name"]
        issues = get_issues(repo_name)
        for issue in issues:
            if issue.get("pull_request"):
                continue
            pr_url = get_pull_request_from_issue(repo_name, issue["number"])
            if pr_url:
                before_code_url, after_code_url = get_code_before_after(pr_url)
                languages = get_languages(repo_name)
                affected_files = get_affected_files(pr_url)
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO fixed_issues VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (issue["html_url"], repo_name, pr_url, languages, before_code_url, after_code_url, affected_files),
                )
        conn.commit()
    conn.close()

if __name__ == "__main__":
    create_db()
    repos = get_mit_repos(pages=10)
    print(f"Found {len(repos)} MIT repositories")
    populate_db(repos)
    print("Database populated successfully.")
