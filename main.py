from .rss_collector import collect
from .scorer import run as score_run
from .email_sender import send_email
from .db import init_db

def main():
    init_db()
    collect()
    score_run(limit=100)
    send_email()

if __name__ == "__main__":
    main()
