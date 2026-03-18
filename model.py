"""
E-Commerce Customer Churn Prediction Model
Uses the Olist Brazilian E-Commerce dataset (or synthetic data for demo)
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    classification_report, roc_auc_score,
    confusion_matrix, roc_curve
)
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
import xgboost as xgb
import shap
import joblib
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# 1.  SYNTHETIC DATA GENERATOR (for demo)
#     Replace with Olist CSV loading in production
# ─────────────────────────────────────────────

def generate_synthetic_ecommerce_data(n=3000, seed=42):
    """
    Generates a realistic synthetic e-commerce customer dataset.
    In production, replace this with:
        df = pd.read_csv('olist_customers_dataset.csv')  (merged Olist tables)
    """
    np.random.seed(seed)
    n_churn   = int(n * 0.27)   # ~27 % churn rate (realistic for e-commerce)
    n_active  = n - n_churn

    def make_group(size, churned):
        return pd.DataFrame({
            "customer_id":            [f"C{i:05d}" for i in range(size)],
            "total_orders":           np.random.poisson(3 if not churned else 1.2, size),
            "avg_order_value":        np.round(np.random.gamma(4, 30 if not churned else 18, size), 2),
            "days_since_last_order":  np.random.randint(1, 60 if not churned else 200, size),
            "total_spend":            np.round(np.random.gamma(5, 50 if not churned else 25, size), 2),
            "num_reviews":            np.random.poisson(2 if not churned else 0.5, size),
            "avg_review_score":       np.clip(np.random.normal(4.1 if not churned else 2.8, 0.9, size), 1, 5).round(1),
            "num_categories":         np.random.randint(1, 8 if not churned else 4, size),
            "used_voucher":           np.random.binomial(1, 0.35 if not churned else 0.55, size),
            "payment_type":           np.random.choice(["credit_card", "boleto", "voucher", "debit_card"],
                                                        size, p=[0.55, 0.25, 0.12, 0.08]),
            "customer_state":         np.random.choice(
                                        ["SP","RJ","MG","RS","PR","SC","BA","GO"],
                                        size, p=[0.42,0.13,0.11,0.08,0.08,0.06,0.07,0.05]),
            "days_as_customer":       np.random.randint(30, 730, size),
            "support_tickets":        np.random.poisson(0.3 if not churned else 1.8, size),
            "late_deliveries":        np.random.poisson(0.1 if not churned else 0.6, size),
            "churn":                  [int(churned)] * size,
        })

    df = pd.concat([make_group(n_active, False),
                    make_group(n_churn,  True)], ignore_index=True)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────
# 2.  OLIST REAL DATA LOADER
#     Pass a folder path containing all Olist CSVs
# ─────────────────────────────────────────────

def load_olist_data(folder: str) -> pd.DataFrame:
    """
    Merges the Olist CSV files into one customer-level feature DataFrame.

    Required files in `folder`:
        olist_customers_dataset.csv
        olist_orders_dataset.csv
        olist_order_items_dataset.csv
        olist_order_payments_dataset.csv
        olist_order_reviews_dataset.csv

    Returns a DataFrame with the same column schema as the synthetic data,
    ready to pass straight into engineer_features() and train_model().
    """
    import os

    # ── Load raw tables ──
    customers = pd.read_csv(os.path.join(folder, "olist_customers_dataset.csv"))
    orders    = pd.read_csv(os.path.join(folder, "olist_orders_dataset.csv"))
    # Parse date columns safely (only if they exist)
    for col in ["order_purchase_timestamp", "order_delivered_customer_date",
                "order_estimated_delivery_date", "order_approved_at",
                "order_delivered_carrier_date"]:
        if col in orders.columns:
            orders[col] = pd.to_datetime(orders[col], errors="coerce")
    items     = pd.read_csv(os.path.join(folder, "olist_order_items_dataset.csv"))
    payments  = pd.read_csv(os.path.join(folder, "olist_order_payments_dataset.csv"))
    reviews   = pd.read_csv(os.path.join(folder, "olist_order_reviews_dataset.csv"))

    # ── Keep only delivered orders ──
    orders = orders[orders["order_status"] == "delivered"].copy()

    # Parse purchase timestamp if not already done
    if "order_purchase_timestamp" not in orders.columns:
        # Try common alternatives
        for alt in ["order_approved_at", "order_estimated_delivery_date"]:
            if alt in orders.columns:
                orders["order_purchase_timestamp"] = pd.to_datetime(orders[alt], errors="coerce")
                break
        else:
            orders["order_purchase_timestamp"] = pd.Timestamp.now()
    else:
        orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")

    # Reference date = 1 day after the latest order in the dataset
    ref_date = orders["order_purchase_timestamp"].max() + pd.Timedelta(days=1)

    # ── Order-level aggregations ──
    order_agg = (
        orders.groupby("customer_id")
        .agg(
            total_orders          = ("order_id", "count"),
            last_order_date       = ("order_purchase_timestamp", "max"),
            first_order_date      = ("order_purchase_timestamp", "min"),
        )
        .reset_index()
    )
    order_agg["days_since_last_order"] = (
        ref_date - order_agg["last_order_date"]
    ).dt.days
    order_agg["days_as_customer"] = (
        ref_date - order_agg["first_order_date"]
    ).dt.days

    # ── Payment aggregations ──
    pay_agg = (
        payments.groupby("order_id")
        .agg(order_value=("payment_value", "sum"),
             payment_type=("payment_type", "first"))
        .reset_index()
    )
    # Map order → customer
    order_customer = orders[["order_id", "customer_id"]]
    pay_agg = pay_agg.merge(order_customer, on="order_id", how="left")

    pay_cust = (
        pay_agg.groupby("customer_id")
        .agg(
            total_spend     = ("order_value", "sum"),
            avg_order_value = ("order_value", "mean"),
            used_voucher    = ("payment_type", lambda x: int("voucher" in x.values)),
            payment_type    = ("payment_type", "first"),
        )
        .reset_index()
    )

    # ── Item aggregations (number of product categories) ──
    items_order = items.merge(order_customer, on="order_id", how="left")
    cat_agg = (
        items_order.groupby("customer_id")
        .agg(num_categories=("product_id", "nunique"))
        .reset_index()
    )

    # ── Review aggregations ──
    rev_order = reviews.merge(order_customer, on="order_id", how="left")
    rev_agg = (
        rev_order.groupby("customer_id")
        .agg(
            num_reviews     = ("review_id", "count"),
            avg_review_score= ("review_score", "mean"),
        )
        .reset_index()
    )

    # ── Late delivery flag (only if both date columns exist) ──
    if "order_delivered_customer_date" in orders.columns and "order_estimated_delivery_date" in orders.columns:
        orders["late"] = (
            orders["order_delivered_customer_date"] >
            orders["order_estimated_delivery_date"]
        ).astype(int)
    else:
        orders["late"] = 0
    late_agg = (
        orders.groupby("customer_id")
        .agg(late_deliveries=("late", "sum"))
        .reset_index()
    )

    # ── Merge everything ──
    df = customers[["customer_id", "customer_state"]].drop_duplicates("customer_id")
    for right in [order_agg, pay_cust, cat_agg, rev_agg, late_agg]:
        df = df.merge(right, on="customer_id", how="left")

    # ── Fill missing values ──
    df["num_reviews"]      = df["num_reviews"].fillna(0)
    df["avg_review_score"] = df["avg_review_score"].fillna(3.0)
    df["num_categories"]   = df["num_categories"].fillna(1)
    df["late_deliveries"]  = df["late_deliveries"].fillna(0)
    df["used_voucher"]     = df["used_voucher"].fillna(0)
    df["payment_type"]     = df["payment_type"].fillna("credit_card")
    df["support_tickets"]  = 0   # not in Olist — set to 0

    # Drop customers with no orders
    df = df.dropna(subset=["total_orders"]).reset_index(drop=True)

    # ── Churn label: bottom 30% recency = churned (relative to dataset) ──
    # This avoids the problem of old datasets where everyone looks churned
    threshold_days = df["days_since_last_order"].quantile(0.70)
    df["churn"] = (df["days_since_last_order"] > threshold_days).astype(int)
    print(f"Churn threshold: {threshold_days:.0f} days | Churn rate: {df['churn'].mean():.1%}")

    # Rename state column to match schema
    df = df.rename(columns={"customer_state": "customer_state"})

    # Drop intermediate date columns
    df = df.drop(columns=["last_order_date", "first_order_date"], errors="ignore")

    print(f"Olist data loaded: {len(df):,} customers | "
          f"churn rate: {df['churn'].mean():.1%}")
    return df


# ─────────────────────────────────────────────
# 3.  FEATURE ENGINEERING
# ─────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # RFM-style features
    df["orders_per_month"]     = df["total_orders"] / (df["days_as_customer"] / 30 + 1)
    df["spend_per_order"]      = df["total_spend"]  / (df["total_orders"] + 1)
    df["recency_score"]        = 1 / (df["days_since_last_order"] + 1)

    # Engagement quality
    df["review_rate"]          = df["num_reviews"] / (df["total_orders"] + 1)
    df["ticket_rate"]          = df["support_tickets"] / (df["total_orders"] + 1)
    df["late_delivery_rate"]   = df["late_deliveries"] / (df["total_orders"] + 1)

    # Encode categoricals
    le = LabelEncoder()
    df["payment_type_enc"]     = le.fit_transform(df["payment_type"])
    df["state_enc"]            = le.fit_transform(df["customer_state"])

    return df


FEATURE_COLS = [
    "total_orders", "avg_order_value", "days_since_last_order",
    "total_spend", "num_reviews", "avg_review_score",
    "num_categories", "used_voucher", "days_as_customer",
    "support_tickets", "late_deliveries",
    # engineered
    "orders_per_month", "spend_per_order", "recency_score",
    "review_rate", "ticket_rate", "late_delivery_rate",
    "payment_type_enc", "state_enc",
]


# ─────────────────────────────────────────────
# 3.  TRAIN
# ─────────────────────────────────────────────

def train_model(df: pd.DataFrame):
    df = engineer_features(df)

    X = df[FEATURE_COLS]
    y = df["churn"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42,
        use_label_encoder=False,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # ── Metrics ──
    y_pred      = model.predict(X_test)
    y_proba     = model.predict_proba(X_test)[:, 1]
    auc         = roc_auc_score(y_test, y_proba)
    report      = classification_report(y_test, y_pred, output_dict=True)
    cm          = confusion_matrix(y_test, y_pred)
    fpr, tpr, _ = roc_curve(y_test, y_proba)

    # ── SHAP explainer ──
    explainer   = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    metrics = {
        "auc":         round(auc, 4),
        "accuracy":    round(report["accuracy"], 4),
        "precision":   round(report["1"]["precision"], 4),
        "recall":      round(report["1"]["recall"], 4),
        "f1":          round(report["1"]["f1-score"], 4),
        "cm":          cm,
        "fpr":         fpr,
        "tpr":         tpr,
        "report":      report,
    }

    artifacts = {
        "model":        model,
        "explainer":    explainer,
        "shap_values":  shap_values,
        "X_test":       X_test,
        "y_test":       y_test,
        "feature_cols": FEATURE_COLS,
    }

    return metrics, artifacts


# ─────────────────────────────────────────────
# 4.  PREDICT ON NEW DATA
# ─────────────────────────────────────────────

def predict_churn(model, new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Accepts a raw customer DataFrame (same columns as training data),
    returns the DataFrame with churn_probability and risk_label appended.
    """
    df = engineer_features(new_df)
    proba = model.predict_proba(df[FEATURE_COLS])[:, 1]

    result = new_df.copy()
    result["churn_probability"] = proba.round(4)
    result["risk_label"] = pd.cut(
        proba,
        bins=[0, 0.33, 0.66, 1.0],
        labels=["🟢 Low", "🟡 Medium", "🔴 High"],
    )
    return result.sort_values("churn_probability", ascending=False)


# ─────────────────────────────────────────────
# 5.  SAVE / LOAD
# ─────────────────────────────────────────────

def save_model(model, path="churn_model.joblib"):
    joblib.dump(model, path)
    print(f"Model saved → {path}")

def load_model(path="churn_model.joblib"):
    return joblib.load(path)


# ─────────────────────────────────────────────
# 6.  QUICK CLI TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating synthetic data …")
    df = generate_synthetic_ecommerce_data(n=3000)

    print("Training XGBoost model …")
    metrics, artifacts = train_model(df)

    print("\n─── Model Performance ───")
    print(f"  AUC-ROC   : {metrics['auc']}")
    print(f"  Accuracy  : {metrics['accuracy']}")
    print(f"  Precision : {metrics['precision']}")
    print(f"  Recall    : {metrics['recall']}")
    print(f"  F1-Score  : {metrics['f1']}")

    save_model(artifacts["model"])
    print("\nDone! Run `streamlit run app.py` to launch the dashboard.")
