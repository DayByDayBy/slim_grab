import requests
import sqlite3
import json
import time
import os
import re
from dotenv import load_dotenv

# uses dotenv in local dir

load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    raise ValueError("gh token is missing")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def save_progress(processed_repo_names):
    with open("progress.json", "w") as f:
        json.dump(processed_repo_names, f)

def load_progress():
    try:
        with open("progress.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


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
    """rate limits etc handler"""
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response
        elif response.status_code == 403 and "X-RateLimit-Reset" in response.headers:
            reset_time = int(response.headers["X-RateLimit-Reset"])
            sleep_time = max(0, reset_time - time.time())
            print(f"rate limit exceeded. sleepytime for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
        elif response.status_code in [502, 503, 504]:  # server error cocdes
            print(f"temp error ({response.status_code}). retrying in 5 seconds...")
            time.sleep(5)
        else:
            print(f"request failed: {response.status_code} for URL: {url}")
            return None

def get_mit_repos(query="stars:>10000", per_page=100, pages=100):
    repos = []
    for page in range(1, pages + 1):
        url = f"https://api.github.com/search/repositories?q={query}+license:mit&sort=forks&order=desc&per_page={per_page}&page={page}"
        response = make_request(url)
        if response:
            data = response.json()
            items = data.get("items", [])
            repos.extend(items)
            print(f"{len(items)} repos on page {page}/{pages} found")
        else:
            print(f"failed to fetch repos (page {page})")
            break
    return repos

def get_languages(repo_name):
    url = f"https://api.github.com/repos/{repo_name}/languages"
    response = make_request(url)
    return json.dumps(list(response.json().keys())) if response else "[]"

def get_affected_files(pr_url):
    if not pr_url:
        return "[]"
    #  html URL to API URL flipper
    if "github.com" in pr_url:
        parts = pr_url.split("/")
        owner = parts[-4]
        repo = parts[-3]
        pr_number = parts[-1]
        files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    else:
        files_url = pr_url + "/files"
    
    response = make_request(files_url)
    if response and response.json():
        return json.dumps([file["filename"] for file in response.json()])
    return "[]"

def get_merged_prs(repo_name, per_page=30, pages=3):
    """get merged pull requests for a repo"""
    prs = []
    total_prs = 0
    
    print(f"fetchin merged PRs for {repo_name}...")
    
    for page in range(1, pages + 1):
        url = f"https://api.github.com/repos/{repo_name}/pulls?state=closed&sort=updated&direction=desc&per_page={per_page}&page={page}"
        response = make_request(url)
        if response:
            data = response.json()
            # include PRs that were actually merged
            merged_prs = [pr for pr in data if pr.get("merged_at")]
            prs.extend(merged_prs)
            total_prs += len(merged_prs)
            print(f"  Page {page}: Found {len(merged_prs)} merged PRs")
        else:
            print(f"Failed to fetch PRs for {repo_name} (page {page})")
            break
            
        # a wee rate limit slow down
        time.sleep(1)
        
    print(f"Found total of {total_prs} merged PRs for {repo_name}")
    return prs

def get_issues_from_pr(pr_data, repo_name):
    """get linked issues from a pull request"""
    # Check PR body for issue references
    body = pr_data.get("body", "")
    if not body:
        return []
    
    # common issue reference patterns
    linked_issues = []
    
    # pattern: "fixes #123", "closes #123", etc.
    patterns = [
        r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)',
        r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+' + repo_name.replace('/', '\/') + r'#(\d+)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, body, re.IGNORECASE)
        for issue_num in matches:
            issue_url = f"https://github.com/{repo_name}/issues/{issue_num}"
            linked_issues.append(issue_url)
    
    return linked_issues

def populate_db_from_prs(repos):
    conn = sqlite3.connect("fixed_issues.db")
    cursor = conn.cursor()
    total_added = 0
    
    for repo in repos:
        repo_name = repo["full_name"]
        added_for_repo = 0
        
        print(f"\n processing repo: {repo_name}")
        
        # get repo languages once to avoid repeated API calls
        languages = get_languages(repo_name)
        print(f"languages used by {repo_name}: {languages}")
        
        prs = get_merged_prs(repo_name)
        if not prs:
            print(f"no PRs found for {repo_name}, skipping it")
            continue
            
        print(f"processing {len(prs)} PRs for {repo_name}")
        
        for pr in prs:
            pr_url = pr["html_url"]
            linked_issues = get_issues_from_pr(pr, repo_name)
            
            if linked_issues:
                print(f"PR {pr['number']} links to {len(linked_issues)} issues")
                
                # get before/after code URLs
                base_sha = pr.get("base", {}).get("sha")
                head_sha = pr.get("head", {}).get("sha")
                before_code_url = f"https://github.com/{repo_name}/commit/{base_sha}" if base_sha else None
                after_code_url = f"https://github.com/{repo_name}/commit/{head_sha}" if head_sha else None
                
                # fet affected files
                affected_files = get_affected_files(pr_url)
                
                # save each linked issue
                for issue_url in linked_issues:
                    try:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO fixed_issues VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (issue_url, repo_name, pr_url, languages, before_code_url, after_code_url, affected_files),
                        )
                        if cursor.rowcount > 0:
                            added_for_repo += 1
                            total_added += 1
                    except sqlite3.Error as e:
                        print(f".db error: {e} for issue {issue_url}")
                
            # commit periodically to avoid losing progress on failure
            if added_for_repo > 0 and added_for_repo % 10 == 0:
                conn.commit()
                print(f"Committed {added_for_repo} entries for {repo_name}")
            
            # baked-in delay to avoid hitting rate limits too quickly
            time.sleep(0.5)
        
        # final commit for this repo
        conn.commit()
        print(f"{added_for_repo} entries for {repo_name} added")
    
    conn.close()
    return total_added

def check_db():
    """Check database contents and print summary stats"""
    conn = sqlite3.connect("fixed_issues.db")
    cursor = conn.cursor()
    
    # get total count
    cursor.execute("SELECT COUNT(*) FROM fixed_issues")
    count = cursor.fetchone()[0]
    print(f"\n .db contains {count} total entries")
    
    if count > 0:
        # repos with most entries, figure more is better than less
        cursor.execute("""
            SELECT repo_name, COUNT(*) as count 
            FROM fixed_issues 
            GROUP BY repo_name 
            ORDER BY count DESC 
            LIMIT 5
        """)
        print("\ntop repos (by entries):")
        for repo, entries in cursor.fetchall():
            print(f"  {repo}: {entries} entries")
        
        # sample entries for terminal
        cursor.execute("SELECT * FROM fixed_issues LIMIT 3")
        print("\nSample entries:")
        for row in cursor.fetchall():
            print(f"  Issue: {row[0]}")
            print(f"  Repo: {row[1]}")
            print(f"  PR: {row[2]}")
            print(f"  Languages: {row[3]}")
            print(f"  Files: {row[6]}")
            print()
    
    conn.close()

    
    
    
if __name__ == "__main__":
    print("starting...")
    
    create_db()
    
    # get all repos to process
    repos = get_mit_repos(query="stars:>10000", per_page=100, pages=1000)
    print(f"\n {len(repos)} MIT repos found")
    
    if not repos:
        print("no repos found")
        exit()
    
    # loading prev processed repos
    processed_repo_names = load_progress()
    print(f"Found {len(processed_repo_names)} previously processed repos")
    
    # filtering out already processed repos
    repos_to_process = [repo for repo in repos if repo["full_name"] not in processed_repo_names]
    print(f"Will process {len(repos_to_process)} new repos")
    
    total_count = 0
    for repo in repos_to_process:
        # process one repo at a time
        count = populate_db_from_prs([repo])
        total_count += count
        
        # save progress after each repo
        processed_repo_names.append(repo["full_name"])
        save_progress(processed_repo_names)
        print(f"Progress saved. Processed {len(processed_repo_names)}/{len(repos)} repos")
    
    print(f"\n {total_count} issue-PR pairs added to .db")
    
    # .db contents verification
    check_db()
    
    print("\n done! \n")