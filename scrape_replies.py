"""Scrape replies to your recent tweets on X via twitter-cli.

Usage:
  python3 scrape_replies.py              — Uses X_HANDLE env var or default
  python3 scrape_replies.py nabotweet    — Scrapes specific handle
"""
import sys
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
TWITTER_CLI = Path.home() / "Library" / "Python" / "3.9" / "bin" / "twitter"
REPLIES_FILE = BASE_DIR / "knowledge" / "engagement" / "replies.json"

HANDLE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("X_HANDLE", "nabotweet")
MAX_TWEETS = 10
MAX_REPLIES = 20


def get_recent_tweets(handle, count):
    """Fetch recent tweets with their IDs."""
    result = subprocess.run(
        [str(TWITTER_CLI), "user-posts", handle, "-n", str(count), "--json"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Failed to fetch tweets: {result.stderr.strip()}")
        return []

    try:
        lines = result.stdout.strip().split("\n")
        json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("["))
        raw = "\n".join(lines[json_start:])
        return json.loads(raw)
    except (StopIteration, json.JSONDecodeError) as e:
        print(f"Failed to parse tweets: {e}")
        return []


def get_replies(tweet_id, max_replies):
    """Fetch replies to a specific tweet."""
    result = subprocess.run(
        [str(TWITTER_CLI), "tweet", str(tweet_id), "-n", str(max_replies), "--json"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return []

    try:
        lines = result.stdout.strip().split("\n")
        json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{") or line.strip().startswith("["))
        raw = "\n".join(lines[json_start:])
        data = json.loads(raw)

        # data might be a dict with tweet + replies, or just the tweet
        if isinstance(data, dict):
            return data.get("replies", [])
        elif isinstance(data, list):
            # Skip first item (original tweet), rest are replies
            return data[1:] if len(data) > 1 else []
        return []
    except (StopIteration, json.JSONDecodeError):
        return []


def main():
    print(f"Scraping replies for @{HANDLE}...\n")

    tweets = get_recent_tweets(HANDLE, MAX_TWEETS)
    if not tweets:
        print("No tweets found.")
        return

    all_replies = []

    for tweet in tweets:
        tweet_id = tweet.get("id") or tweet.get("id_str") or tweet.get("rest_id")
        text = tweet.get("text", tweet.get("full_text", ""))[:100]
        metrics = tweet.get("metrics", {})
        reply_count = metrics.get("replies", 0) if isinstance(metrics, dict) else tweet.get("reply_count", 0)

        if not tweet_id or reply_count == 0:
            continue

        print(f"Tweet: \"{text}...\" ({reply_count} replies)")

        replies = get_replies(tweet_id, MAX_REPLIES)

        if replies:
            reply_list = []
            for r in replies:
                # Handle both nested author object and flat structure
                author_obj = r.get("author", {})
                if isinstance(author_obj, dict):
                    author = author_obj.get("screenName", author_obj.get("screen_name", ""))
                else:
                    author = r.get("screenName", r.get("screen_name", ""))

                reply_text = r.get("text", r.get("full_text", ""))
                reply_id = r.get("id") or r.get("id_str") or ""
                r_metrics = r.get("metrics", {})

                reply_list.append({
                    "author": f"@{author}" if author else "",
                    "text": reply_text,
                    "url": f"https://x.com/{author}/status/{reply_id}" if author and reply_id else "",
                    "time": r.get("createdAt", r.get("created_at", "")),
                    "metrics": {
                        "reply": r_metrics.get("replies", 0) if isinstance(r_metrics, dict) else 0,
                        "retweet": r_metrics.get("retweets", 0) if isinstance(r_metrics, dict) else 0,
                        "like": r_metrics.get("likes", 0) if isinstance(r_metrics, dict) else 0,
                    },
                })

                print(f"    @{author}: \"{reply_text[:60]}{'...' if len(reply_text) > 60 else ''}\"")

            all_replies.append({
                "tweet_text": text,
                "tweet_url": f"https://x.com/{HANDLE}/status/{tweet_id}",
                "tweet_id": str(tweet_id),
                "replies": reply_list,
                "scraped_at": datetime.now().isoformat(),
            })

        print()

    # Save replies
    REPLIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPLIES_FILE, "w") as f:
        json.dump(all_replies, f, indent=2, ensure_ascii=False)

    total_replies = sum(len(t["replies"]) for t in all_replies)
    print(f"Saved replies from {len(all_replies)} tweets to {REPLIES_FILE}")
    print(f"Total replies scraped: {total_replies}")


if __name__ == "__main__":
    main()
