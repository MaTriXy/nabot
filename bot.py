"""
NaBot - AI co-writing tweet bot
Generates tweets/day, queues for approval, posts approved ones.

Usage:
  python3 bot.py generate        — Generate tweets for today
  python3 bot.py approve         — Review and approve/reject queued tweets
  python3 bot.py post            — Post approved tweets to X.com
  python3 bot.py analyze         — Analyze engagement on recent tweets
  python3 bot.py status          — Show current queue status
  python3 bot.py replies         — Scrape replies to recent tweets
  python3 bot.py reply-add "text" reply_url  — Add a reply (reply_url = the tweet you're responding to)
  python3 bot.py reply-approve   — Review and approve/reject queued replies
  python3 bot.py reply-post      — Post approved replies to X.com
  python3 bot.py reply-status    — Show reply queue status

Configuration:
  Set your X handle in config or pass as environment variable:
    export X_HANDLE=your_handle
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).parent
TWITTER_CLI = Path.home() / "Library" / "Python" / "3.9" / "bin" / "twitter"
TWEETS_DIR = BASE_DIR / "tweets"
QUEUE_FILE = TWEETS_DIR / "queue.json"
POSTED_FILE = TWEETS_DIR / "posted.json"
ENGAGEMENT_FILE = BASE_DIR / "knowledge" / "engagement" / "engagement_log.json"
REPLIES_FILE = BASE_DIR / "knowledge" / "engagement" / "replies.json"
REPLY_QUEUE_FILE = TWEETS_DIR / "reply_queue.json"
X_HANDLE = os.environ.get("X_HANDLE", "your_handle")


def load_json(path, default=None):
    if default is None:
        default = []
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_tweets():
    """Generate tweets and add to queue for approval."""
    queue = load_json(QUEUE_FILE)
    today = date.today().isoformat()

    today_tweets = [t for t in queue if t.get("generated_date") == today]
    if today_tweets:
        print(f"Already generated {len(today_tweets)} tweets for today.")
        print("Run 'python3 bot.py approve' to review them.")
        return

    print("Generating tweets...")
    print("Use Claude Code to generate tweets with the x-tweet skill:")
    print()
    print('  Just tell Claude: "generate tweets for today"')
    print("  Claude will use the x-tweet skill and context profiles.")
    print()
    print("Then add them to the queue with:")
    print('  python3 bot.py add "tweet text here"')


def add_tweet(text):
    """Add a tweet to the approval queue."""
    queue = load_json(QUEUE_FILE)
    tweet = {
        "id": len(queue) + 1,
        "text": text,
        "status": "pending",
        "generated_date": date.today().isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    queue.append(tweet)
    save_json(QUEUE_FILE, queue)
    print(f"Tweet #{tweet['id']} added to queue (pending approval).")
    print(f"  \"{text[:80]}{'...' if len(text) > 80 else ''}\"")


def approve_tweets():
    """Interactive approval of queued tweets."""
    queue = load_json(QUEUE_FILE)
    pending = [t for t in queue if t["status"] == "pending"]

    if not pending:
        print("No tweets pending approval.")
        return

    print(f"\n{len(pending)} tweet(s) pending approval:\n")

    for tweet in pending:
        print(f"--- Tweet #{tweet['id']} ({tweet['generated_date']}) ---")
        print(f"{tweet['text']}")
        print()

        while True:
            choice = input("[a]pprove / [r]eject / [e]dit / [s]kip? ").strip().lower()
            if choice == "a":
                tweet["status"] = "approved"
                tweet["approved_at"] = datetime.now().isoformat()
                print("Approved!")
                break
            elif choice == "r":
                tweet["status"] = "rejected"
                print("Rejected.")
                break
            elif choice == "e":
                new_text = input("New text: ").strip()
                if new_text:
                    tweet["text"] = new_text
                    tweet["status"] = "approved"
                    tweet["approved_at"] = datetime.now().isoformat()
                    tweet["edited"] = True
                    print("Edited and approved!")
                break
            elif choice == "s":
                print("Skipped.")
                break

        print()

    save_json(QUEUE_FILE, queue)
    approved = len([t for t in queue if t["status"] == "approved" and not t.get("posted")])
    print(f"\n{approved} tweet(s) ready to post. Run 'python3 bot.py post' to publish.")


def post_tweets():
    """Post approved tweets to X.com via twitter-cli."""
    queue = load_json(QUEUE_FILE)
    posted = load_json(POSTED_FILE)
    to_post = [t for t in queue if t["status"] == "approved" and not t.get("posted")]

    if not to_post:
        print("No approved tweets to post.")
        return

    print(f"Posting {len(to_post)} tweet(s) via twitter-cli...\n")

    for tweet in to_post:
        print(f"Posting tweet #{tweet['id']}: \"{tweet['text'][:60]}...\"")

        try:
            result = subprocess.run(
                [str(TWITTER_CLI), "post", tweet["text"]],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                print(f"  Failed: {result.stderr.strip()}")
                tweet["post_error"] = result.stderr.strip()
                continue

            tweet["posted"] = True
            tweet["posted_at"] = datetime.now().isoformat()
            tweet["status"] = "posted"
            posted.append(tweet)
            print(f"  Posted!")

            # Parse tweet ID from output if available
            output = result.stdout.strip()
            if output:
                tweet["post_output"] = output

            time.sleep(2)

        except Exception as e:
            print(f"  Failed to post: {e}")
            tweet["post_error"] = str(e)

    save_json(QUEUE_FILE, queue)
    save_json(POSTED_FILE, posted)

    print(f"\nDone. {len([t for t in to_post if t.get('posted')])} tweets posted.")


def analyze_engagement():
    """Scrape engagement metrics via twitter-cli."""
    print(f"Analyzing engagement for @{X_HANDLE}...\n")

    result = subprocess.run(
        [str(TWITTER_CLI), "user-posts", X_HANDLE, "-n", "10", "--json"],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        print(f"Failed to fetch tweets: {result.stderr.strip()}")
        return

    try:
        lines = result.stdout.strip().split("\n")
        json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("["))
        raw = "\n".join(lines[json_start:])
        tweets = json.loads(raw)
    except (StopIteration, json.JSONDecodeError) as e:
        print(f"Failed to parse output: {e}")
        return

    engagement_data = load_json(ENGAGEMENT_FILE)

    for t in tweets:
        text = t.get("text", "")
        metrics = {
            "reply": str(t.get("reply_count", 0)),
            "retweet": str(t.get("retweet_count", 0)),
            "like": str(t.get("favorite_count", 0)),
        }
        views = t.get("views_count", t.get("view_count", "N/A"))

        print(f"Tweet: \"{text[:60]}...\"")
        print(f"  Replies: {metrics['reply']} | Retweets: {metrics['retweet']} | Likes: {metrics['like']} | Views: {views}")

        engagement_data.append({
            "text": text,
            "metrics": metrics,
            "views": views,
            "scraped_at": datetime.now().isoformat(),
        })

    save_json(ENGAGEMENT_FILE, engagement_data)
    print(f"\nEngagement data saved to {ENGAGEMENT_FILE}")


def scrape_replies():
    """Scrape replies to recent tweets."""
    import subprocess
    result = subprocess.run([sys.executable, str(BASE_DIR / "scrape_replies.py")], cwd=str(BASE_DIR))
    if result.returncode != 0:
        print("Failed to scrape replies.")
        return

    replies_data = load_json(REPLIES_FILE)
    total = sum(len(t["replies"]) for t in replies_data)
    print(f"\n{total} replies loaded. Use Claude to generate responses:")
    print('  Tell Claude: "generate replies to recent tweet responses"')
    print("  Then: python3 bot.py reply-approve")


def add_reply(text, tweet_url):
    """Add a reply to the approval queue."""
    queue = load_json(REPLY_QUEUE_FILE)
    reply = {
        "id": len(queue) + 1,
        "text": text,
        "tweet_url": tweet_url,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    queue.append(reply)
    save_json(REPLY_QUEUE_FILE, queue)
    print(f"Reply #{reply['id']} added to queue (pending approval).")
    print(f"  To: {tweet_url}")
    print(f"  \"{text[:80]}{'...' if len(text) > 80 else ''}\"")


def approve_replies():
    """Interactive approval of queued replies."""
    queue = load_json(REPLY_QUEUE_FILE)
    pending = [r for r in queue if r["status"] == "pending"]

    if not pending:
        print("No replies pending approval.")
        return

    print(f"\n{len(pending)} reply(ies) pending approval:\n")

    for reply in pending:
        print(f"--- Reply #{reply['id']} ---")
        print(f"To: {reply['tweet_url']}")
        print(f"{reply['text']}")
        print()

        while True:
            choice = input("[a]pprove / [r]eject / [e]dit / [s]kip? ").strip().lower()
            if choice == "a":
                reply["status"] = "approved"
                reply["approved_at"] = datetime.now().isoformat()
                print("Approved!")
                break
            elif choice == "r":
                reply["status"] = "rejected"
                print("Rejected.")
                break
            elif choice == "e":
                new_text = input("New text: ").strip()
                if new_text:
                    reply["text"] = new_text
                    reply["status"] = "approved"
                    reply["approved_at"] = datetime.now().isoformat()
                    reply["edited"] = True
                    print("Edited and approved!")
                break
            elif choice == "s":
                print("Skipped.")
                break

        print()

    save_json(REPLY_QUEUE_FILE, queue)
    approved = len([r for r in queue if r["status"] == "approved" and not r.get("posted")])
    print(f"\n{approved} reply(ies) ready to post. Run 'python3 bot.py reply-post' to publish.")


def post_replies():
    """Post approved replies to X.com via twitter-cli."""
    queue = load_json(REPLY_QUEUE_FILE)
    to_post = [r for r in queue if r["status"] == "approved" and not r.get("posted")]

    if not to_post:
        print("No approved replies to post.")
        return

    print(f"Posting {len(to_post)} reply(ies) via twitter-cli...\n")

    for reply in to_post:
        print(f"Replying to: {reply['tweet_url']}")
        print(f"  Text: \"{reply['text'][:60]}...\"")

        try:
            # Extract status ID from tweet URL
            status_match = re.search(r'/status/(\d+)', reply["tweet_url"])
            if not status_match:
                print(f"  Could not extract status ID from {reply['tweet_url']}")
                continue
            status_id = status_match.group(1)

            result = subprocess.run(
                [str(TWITTER_CLI), "post", reply["text"], "--reply-to", status_id],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                print(f"  Failed: {result.stderr.strip()}")
                reply["post_error"] = result.stderr.strip()
                continue

            reply["posted"] = True
            reply["posted_at"] = datetime.now().isoformat()
            reply["status"] = "posted"
            print(f"  Posted!")

            output = result.stdout.strip()
            if output:
                reply["post_output"] = output

            time.sleep(2)

        except Exception as e:
            print(f"  Failed to post: {e}")
            reply["post_error"] = str(e)

    save_json(REPLY_QUEUE_FILE, queue)

    posted_count = len([r for r in to_post if r.get("posted")])
    print(f"\nDone. {posted_count} replies posted.")


def show_reply_status():
    """Show reply queue status."""
    queue = load_json(REPLY_QUEUE_FILE)

    pending = [r for r in queue if r["status"] == "pending"]
    approved = [r for r in queue if r["status"] == "approved" and not r.get("posted")]
    rejected = [r for r in queue if r["status"] == "rejected"]
    posted = [r for r in queue if r.get("posted")]

    print(f"Reply Queue Status:")
    print(f"  Pending approval: {len(pending)}")
    print(f"  Approved (ready to post): {len(approved)}")
    print(f"  Rejected: {len(rejected)}")
    print(f"  Posted: {len(posted)}")

    if approved:
        print(f"\nReady to post:")
        for r in approved:
            print(f"  #{r['id']}: \"{r['text'][:70]}...\"")
            print(f"         To: {r['tweet_url']}")


def show_status():
    """Show current queue status."""
    queue = load_json(QUEUE_FILE)
    posted = load_json(POSTED_FILE)

    pending = [t for t in queue if t["status"] == "pending"]
    approved = [t for t in queue if t["status"] == "approved" and not t.get("posted")]
    rejected = [t for t in queue if t["status"] == "rejected"]

    print(f"Queue Status:")
    print(f"  Pending approval: {len(pending)}")
    print(f"  Approved (ready to post): {len(approved)}")
    print(f"  Rejected: {len(rejected)}")
    print(f"  Posted (total): {len(posted)}")

    if approved:
        print(f"\nReady to post:")
        for t in approved:
            print(f"  #{t['id']}: \"{t['text'][:70]}...\"")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "generate":
        generate_tweets()
    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: python3 bot.py add \"tweet text\"")
            return
        add_tweet(sys.argv[2])
    elif cmd == "approve":
        approve_tweets()
    elif cmd == "post":
        post_tweets()
    elif cmd == "analyze":
        analyze_engagement()
    elif cmd == "status":
        show_status()
    elif cmd == "replies":
        scrape_replies()
    elif cmd == "reply-add":
        if len(sys.argv) < 4:
            print("Usage: python3 bot.py reply-add \"reply text\" tweet_url")
            return
        add_reply(sys.argv[2], sys.argv[3])
    elif cmd == "reply-approve":
        approve_replies()
    elif cmd == "reply-post":
        post_replies()
    elif cmd == "reply-status":
        show_reply_status()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
