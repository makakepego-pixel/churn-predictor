"""
E-Commerce Churn Prediction Dashboard
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import shap
import io
import tempfile, os
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from model import (
    generate_synthetic_ecommerce_data,
    load_olist_data,
    train_model,
    predict_churn,
    FEATURE_COLS,
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Churn Predictor",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
    .metric-card {
        background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
        border: 1px solid #3a3a5c;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        color: white;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #7c6af7; }
    .metric-label { font-size: 0.85rem; color: #aaa; margin-top: 4px; }
    .risk-high   { color: #ff6b6b; font-weight: 700; }
    .risk-medium { color: #ffd93d; font-weight: 700; }
    .risk-low    { color: #6bcb77; font-weight: 700; }
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        margin: 24px 0 12px;
        padding-bottom: 6px;
        border-bottom: 2px solid #7c6af7;
        color: #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────
with open("auth_config.yaml") as f:
    auth_cfg = yaml.load(f, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    auth_cfg["credentials"],
    auth_cfg["cookie"]["name"],
    auth_cfg["cookie"]["key"],
    auth_cfg["cookie"]["expiry_days"],
)

name, auth_status, username = authenticator.login("🔐 Client Login", "main")

if auth_status is False:
    st.error("Incorrect username or password.")
    st.stop()
elif auth_status is None:
    st.info("Please enter your credentials to access the dashboard.")
    st.markdown("**Demo login:** username  / password ")
    st.stop()

# ── Logged in — show logout in sidebar ──
with st.sidebar:
    st.markdown(f"👋 Welcome, **{name}**")
    authenticator.logout("Logout", "sidebar")
    st.divider()

# ─────────────────────────────────────────────
# SESSION STATE — train model once per data source
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="Training on demo data …")
def get_demo_model():
    df = generate_synthetic_ecommerce_data(n=3000)
    metrics, artifacts = train_model(df)
    return df, metrics, artifacts

@st.cache_resource(show_spinner="Training on real Olist data … (this takes ~30 sec)")
def get_olist_model(cache_key: str, tmpdir: str):
    df = load_olist_data(tmpdir)
    metrics, artifacts = train_model(df)
    return df, metrics, artifacts


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/graph-report.png", width=60)
    st.title("Churn Predictor")
    st.caption("E-Commerce ML Dashboard")
    st.divider()

    st.markdown("### 📂 Data Source")
    data_source = st.radio("", ["Use demo data", "Upload Olist CSVs", "Upload single CSV"], label_visibility="collapsed")

    uploaded_file = None
    olist_files   = {}

    if data_source == "Upload Olist CSVs":
        st.caption("Upload all 5 Olist CSV files:")
        olist_names = [
            "olist_customers_dataset.csv",
            "olist_orders_dataset.csv",
            "olist_order_items_dataset.csv",
            "olist_order_payments_dataset.csv",
            "olist_order_reviews_dataset.csv",
        ]
        for fname in olist_names:
            f = st.file_uploader(fname, type=["csv"], key=fname)
            if f:
                olist_files[fname] = f
        if len(olist_files) < 5:
            st.info(f"{len(olist_files)}/5 files uploaded")

    elif data_source == "Upload single CSV":
        uploaded_file = st.file_uploader(
            "Upload customer CSV",
            type=["csv"],
            help="Must include same columns as training schema."
        )

    st.divider()
    st.markdown("### ⚙️ Prediction Threshold")
    threshold = st.slider("Churn probability cutoff", 0.1, 0.9, 0.5, 0.05)

    st.divider()
    st.markdown("### 📖 About")
    st.info(
        "Built with **XGBoost + SHAP**.\n\n"
        "Predicts which customers are likely to churn so you can take action early."
    )


# ─────────────────────────────────────────────
# RESOLVE ACTIVE MODEL + DATA (outside sidebar scope)
# ─────────────────────────────────────────────
if data_source == "Upload Olist CSVs" and len(olist_files) == 5:
    cache_key = str(sorted([(k, v.size) for k, v in olist_files.items()]))
    if st.session_state.get("olist_cache_key") != cache_key:
        tmpdir = tempfile.mkdtemp()
        for fname, fobj in olist_files.items():
            fobj.seek(0)
            with open(os.path.join(tmpdir, fname), "wb") as out:
                out.write(fobj.read())
        st.session_state["olist_tmpdir"]    = tmpdir
        st.session_state["olist_cache_key"] = cache_key
    tmpdir = st.session_state["olist_tmpdir"]
    df_full, metrics, artifacts = get_olist_model(cache_key, tmpdir)
else:
    df_full, metrics, artifacts = get_demo_model()

model     = artifacts["model"]
explainer = artifacts["explainer"]
shap_vals = artifacts["shap_values"]
X_test    = artifacts["X_test"]

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("# 📉 E-Commerce Churn Prediction Dashboard")
st.markdown("Identify at-risk customers before they leave — powered by XGBoost & SHAP explainability.")
st.divider()

# ─────────────────────────────────────────────
# TAB LAYOUT
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Overview",
    "👥 Customer Risk Table",
    "📊 Model Performance",
    "🔍 SHAP Explainability",
])


# ══════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════
with tab1:
    # ── Resolve prediction dataframe ──
    if data_source == "Upload Olist CSVs" and len(olist_files) == 5:
        # df_full already contains real Olist data (loaded + retrained above)
        df_pred = df_full.drop(columns=["churn"], errors="ignore")
        st.success(f"Model retrained on {len(df_pred):,} real Olist customers ✅")
    elif data_source == "Upload Olist CSVs" and len(olist_files) < 5:
        st.warning(f"Please upload all 5 Olist CSV files ({len(olist_files)}/5 uploaded).")
        df_pred = df_full.drop(columns=["churn"], errors="ignore")
    elif data_source == "Upload single CSV" and uploaded_file:
        try:
            uploaded_file.seek(0)
            df_pred = pd.read_csv(uploaded_file)
            st.success(f"Loaded {len(df_pred):,} customers from your file.")
        except Exception as e:
            st.error(f"Error reading file: {e}")
            df_pred = df_full.drop(columns=["churn"], errors="ignore")
    else:
        df_pred = df_full.drop(columns=["churn"], errors="ignore")

    results = predict_churn(model, df_pred)

    # ── KPI Cards ──
    high   = (results["risk_label"] == "🔴 High").sum()
    medium = (results["risk_label"] == "🟡 Medium").sum()
    low    = (results["risk_label"] == "🟢 Low").sum()
    total  = len(results)
    avg_p  = results["churn_probability"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, label, color in [
        (c1, total,             "Total Customers",  "#7c6af7"),
        (c2, high,              "🔴 High Risk",     "#ff6b6b"),
        (c3, medium,            "🟡 Medium Risk",   "#ffd93d"),
        (c4, low,               "🟢 Low Risk",      "#6bcb77"),
        (c5, f"{avg_p:.1%}",    "Avg Churn Prob",   "#7c6af7"),
    ]:
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:{color}">{val}</div>
            <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Risk Distribution Chart ──
    col_chart, col_pie = st.columns(2)

    with col_chart:
        st.markdown('<div class="section-header">Churn Probability Distribution</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(6, 3), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        ax.hist(results["churn_probability"], bins=40, color="#7c6af7", edgecolor="#1e1e2e", alpha=0.9)
        ax.axvline(threshold, color="#ff6b6b", linestyle="--", linewidth=1.5, label=f"Threshold ({threshold})")
        ax.set_xlabel("Churn Probability", color="white", fontsize=10)
        ax.set_ylabel("# Customers", color="white", fontsize=10)
        ax.tick_params(colors="white")
        for spine in ax.spines.values(): spine.set_edgecolor("#3a3a5c")
        ax.legend(facecolor="#2a2a3e", labelcolor="white", fontsize=9)
        st.pyplot(fig)
        plt.close()

    with col_pie:
        st.markdown('<div class="section-header">Risk Segment Breakdown</div>', unsafe_allow_html=True)
        fig2, ax2 = plt.subplots(figsize=(4, 3), facecolor="#1e1e2e")
        ax2.set_facecolor("#1e1e2e")
        sizes  = [high, medium, low]
        colors = ["#ff6b6b", "#ffd93d", "#6bcb77"]
        labels = ["High", "Medium", "Low"]
        wedges, texts, autotexts = ax2.pie(
            sizes, labels=labels, colors=colors,
            autopct="%1.1f%%", startangle=140,
            textprops={"color": "white", "fontsize": 10},
        )
        for at in autotexts: at.set_color("black")
        st.pyplot(fig2)
        plt.close()


# ══════════════════════════════════════════════
# TAB 2 — CUSTOMER RISK TABLE
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">Customer Risk Scores</div>', unsafe_allow_html=True)

    # Filters
    f1, f2, f3 = st.columns(3)
    risk_filter = f1.multiselect(
        "Risk Level", ["🔴 High", "🟡 Medium", "🟢 Low"],
        default=["🔴 High", "🟡 Medium"]
    )
    min_prob = f2.slider("Min probability", 0.0, 1.0, 0.0, 0.05)
    max_rows = f3.selectbox("Show rows", [25, 50, 100, 200], index=1)

    filtered = results[
        (results["risk_label"].isin(risk_filter)) &
        (results["churn_probability"] >= min_prob)
    ].head(max_rows)

    display_cols = [
        "customer_id", "churn_probability", "risk_label",
        "total_orders", "days_since_last_order",
        "avg_review_score", "support_tickets", "total_spend"
    ]

    st.dataframe(
        filtered[display_cols].style
            .background_gradient(subset=["churn_probability"], cmap="RdYlGn_r")
            .format({"churn_probability": "{:.1%}", "total_spend": "${:,.0f}"}),
        use_container_width=True,
        height=450,
    )

    # Download
    csv = filtered[display_cols].to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download Results CSV",
        data=csv,
        file_name="churn_predictions.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════
# TAB 3 — MODEL PERFORMANCE
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">Model Metrics</div>', unsafe_allow_html=True)

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, key, label in [
        (m1, "auc",       "AUC-ROC"),
        (m2, "accuracy",  "Accuracy"),
        (m3, "precision", "Precision"),
        (m4, "recall",    "Recall"),
        (m5, "f1",        "F1-Score"),
    ]:
        col.metric(label, f"{metrics[key]:.2%}")

    col_roc, col_cm = st.columns(2)

    with col_roc:
        st.markdown('<div class="section-header">ROC Curve</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(5, 4), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        ax.plot(metrics["fpr"], metrics["tpr"], color="#7c6af7", lw=2,
                label=f'AUC = {metrics["auc"]:.3f}')
        ax.plot([0,1],[0,1], linestyle="--", color="#555", lw=1)
        ax.set_xlabel("False Positive Rate", color="white")
        ax.set_ylabel("True Positive Rate", color="white")
        ax.set_title("ROC Curve", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values(): spine.set_edgecolor("#3a3a5c")
        ax.legend(facecolor="#2a2a3e", labelcolor="white")
        st.pyplot(fig); plt.close()

    with col_cm:
        st.markdown('<div class="section-header">Confusion Matrix</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(4, 4), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        cm = metrics["cm"]
        im = ax.imshow(cm, cmap="Purples")
        ax.set_xticks([0,1]); ax.set_yticks([0,1])
        ax.set_xticklabels(["No Churn","Churn"], color="white")
        ax.set_yticklabels(["No Churn","Churn"], color="white")
        ax.set_xlabel("Predicted", color="white")
        ax.set_ylabel("Actual", color="white")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(cm[i,j]), ha="center", va="center",
                        color="white", fontsize=18, fontweight="bold")
        plt.colorbar(im, ax=ax)
        st.pyplot(fig); plt.close()


# ══════════════════════════════════════════════
# TAB 4 — SHAP EXPLAINABILITY
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">Feature Importance (SHAP)</div>', unsafe_allow_html=True)
    st.caption("SHAP explains *why* the model predicts churn for each customer — great to show clients!")

    col_bar, col_bee = st.columns(2)

    with col_bar:
        st.markdown("**Mean |SHAP| — Global Feature Impact**")
        fig, ax = plt.subplots(figsize=(6, 5), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        mean_shap = np.abs(shap_vals).mean(axis=0)
        order     = np.argsort(mean_shap)
        colors    = plt.cm.RdPu(np.linspace(0.3, 0.9, len(FEATURE_COLS)))
        ax.barh(np.array(FEATURE_COLS)[order], mean_shap[order], color=colors)
        ax.tick_params(colors="white", labelsize=8)
        ax.set_xlabel("Mean |SHAP value|", color="white")
        for spine in ax.spines.values(): spine.set_edgecolor("#3a3a5c")
        st.pyplot(fig); plt.close()

    with col_bee:
        st.markdown("**SHAP Summary — Impact Direction**")
        fig, ax = plt.subplots(figsize=(6, 5), facecolor="#1e1e2e")
        shap.summary_plot(
            shap_vals, X_test,
            plot_type="dot",
            show=False,
            color_bar=True,
        )
        fig = plt.gcf()
        fig.set_facecolor("#1e1e2e")
        st.pyplot(fig); plt.close()

    # ── Single customer explanation ──
    st.divider()
    st.markdown('<div class="section-header">🔎 Explain a Single Customer</div>', unsafe_allow_html=True)
    idx = st.slider("Select customer index from test set", 0, len(X_test)-1, 0)

    fig, ax = plt.subplots(figsize=(8, 3), facecolor="#1e1e2e")
    shap.waterfall_plot(
        shap.Explanation(
            values        = shap_vals[idx],
            base_values   = explainer.expected_value,
            data          = X_test.iloc[idx].values,
            feature_names = FEATURE_COLS,
        ),
        show=False
    )
    fig = plt.gcf()
    fig.set_facecolor("#1e1e2e")
    st.pyplot(fig); plt.close()


# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.divider()
st.caption("Built with XGBoost · SHAP · Streamlit · Pandas · Scikit-learn | Portfolio project by [Your Name]")
