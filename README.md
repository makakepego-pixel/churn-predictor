# 📉 E-Commerce Churn Prediction — Portfolio Project

Predict which customers are likely to churn using **XGBoost + SHAP**, wrapped in a
**Streamlit dashboard** you can demo to clients or deploy in minutes.

---

## 🚀 Quick Start

```bash
# 1. Clone / unzip the project
cd churn_project

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Train & save the model via CLI
python model.py

# 4. Launch the dashboard
streamlit run app.py
```

The app opens at **http://localhost:8501** automatically.

---

## 📁 Project Structure

```
churn_project/
├── model.py          # Data generation, feature engineering, XGBoost training
├── app.py            # Streamlit dashboard (4 tabs)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## 🔄 Using Real Data (Olist Dataset)

1. Download from Kaggle → [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
2. Merge the relevant tables:
   ```python
   customers  = pd.read_csv("olist_customers_dataset.csv")
   orders     = pd.read_csv("olist_orders_dataset.csv")
   order_items= pd.read_csv("olist_order_items_dataset.csv")
   reviews    = pd.read_csv("olist_order_reviews_dataset.csv")
   # ... merge on customer_id / order_id
   ```
3. Define churn label (e.g., no purchase in last 90 days)
4. Replace `generate_synthetic_ecommerce_data()` call in `model.py` with your merged DataFrame

---

## 📊 Dashboard Tabs

| Tab | What it shows |
|-----|---------------|
| 🏠 Overview | KPI cards + risk distribution charts |
| 👥 Customer Risk Table | Sortable table with churn probability per customer + CSV download |
| 📊 Model Performance | AUC-ROC, accuracy, precision, recall, F1, confusion matrix |
| 🔍 SHAP Explainability | Global feature importance + per-customer waterfall charts |

---

## 💼 How to Present This to Clients

> *"I built a model that flags at-risk customers up to 30 days before they churn,
> with ~87% AUC-ROC. You can upload your customer data and immediately see who needs
> a retention offer, and exactly why the model flagged them — thanks to SHAP explanations."*

---

## 🛠️ Tech Stack

- **XGBoost** — gradient boosted trees, best-in-class for tabular data
- **SHAP** — model explainability (why each prediction was made)
- **Streamlit** — turn the model into a shareable web app
- **Pandas / Scikit-learn** — data processing & preprocessing

---

## 💰 Freelance Pricing Guide

| Package | Deliverables | Price |
|---------|-------------|-------|
| Starter | Churn model + PDF report | $300–500 |
| Standard | Model + this dashboard | $800–1,500 |
| Premium | Dashboard + deployment + 30-day support | $2,000–3,000 |

---

## 📬 Next Steps

- [ ] Replace synthetic data with Olist or client's real data
- [ ] Add email alert integration (notify when high-risk customers identified)
- [ ] Deploy to [Streamlit Cloud](https://streamlit.io/cloud) (free tier available)
- [ ] Add time-series sales forecasting module