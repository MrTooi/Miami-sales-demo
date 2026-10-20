# MargenX

Profit per job for small print, sign and apparel shops. It reads the sales and cost CSV files a shop already exports, and shows which jobs and customers make or lose money, saying plainly when a figure is incomplete. This is a demonstration with fictional data (sample files in `sample_data/marginx/`).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Connect this GitHub repository to Streamlit Community Cloud and set the main file to `app.py`.

**Demo only:** Do not upload sensitive customer or payment information. No authentication, persistent storage, or production security controls are included.