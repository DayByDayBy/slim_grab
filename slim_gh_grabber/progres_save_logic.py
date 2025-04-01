# state saving introduced bugs before, hence chucking it,
# but i think this is how it might be best acheived, if going that way again 

# ----------


# def save_progress(processed_repos):
#     with open("progress.json", "w") as f:
#         json.dump(processed_repos, f)

# def load_progress():
#     try:
#         with open("progress.json", "r") as f:
#             return json.load(f)
#     except (FileNotFoundError, json.JSONDecodeError):
#         return []
    
    
    
### and:
    
    
    
    
    # if __name__ == "__main__":
    # print("starting...")
    
    # create_db()
    
    # # get all repos to process
    # repos = get_mit_repos(query="stars:>500", per_page=100, pages=100)
    # print(f"\n {len(repos)} MIT repos found")
    
    # if not repos:
    #     print("no repos found")
    #     exit()
    
    # # loading prev processed repos
    # processed_repo_names = load_progress()
    # print(f"Found {len(processed_repo_names)} previously processed repos")
    
    # # filtering out already processed repos
    # repos_to_process = [repo for repo in repos if repo["full_name"] not in processed_repo_names]
    # print(f"Will process {len(repos_to_process)} new repos")
    
    # total_count = 0
    # for repo in repos_to_process:
    #     # process one repo at a time
    #     count = populate_db_from_prs([repo])
    #     total_count += count
        
    #     # save progress after each repo
    #     processed_repo_names.append(repo["full_name"])
    #     save_progress(processed_repo_names)
    #     print(f"Progress saved. Processed {len(processed_repo_names)}/{len(repos)} repos")
    
    # print(f"\n {total_count} issue-PR pairs added to .db")
    
    # # .db contents verification
    # check_db()
    
    # print("\n done! \n")