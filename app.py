import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import shap
import tempfile, os, json, hashlib
from model import (
    generate_synthetic_ecommerce_data,
    load_olist_data,
    train_model,
    predict_churn,
    auto_convert_csv,
    FEATURE_COLS,
)

# ── PAGE CONFIG ── (this hides the "Run with..." and default About menu)
st.set_page_config(
    page_title="Churn Predictor",
    page_icon="📉",
    layout="wide",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# Custom styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
.metric-card { 
    background: linear-gradient(135deg,#1e1e2e,#2a2a3e); 
    border:1px solid #3a3a5c; 
    border-radius:12px; 
    padding:20px; 
    text-align:center; 
    color:white; 
}
.metric-value { font-size:2rem; font-weight:700; color:#7c6af7; }
.metric-label { font-size:0.85rem; color:#aaa; margin-top:4px; }
.section-header { 
    font-size:1.3rem; 
    font-weight:700; 
    margin:24px 0 12px; 
    padding-bottom:6px; 
    border-bottom:2px solid #7c6af7; 
    color:#e0e0e0; 
}
/* Hide any remaining Streamlit tooltips / internal elements if needed */
.stTooltipIcon { display: none !important; }
[data-testid="tooltipHoverTarget"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── USER STORE ──
USERS_FILE = "users.json"
DEFAULT_USERS = {
    "demo_client": {"password_hash": hashlib.sha256("demo123".encode()).hexdigest(), "name": "Demo Client", "role": "client"},
    "admin": {"password_hash": hashlib.sha256("admin123".encode()).hexdigest(), "name": "Admin", "role": "admin"},
}

def load_users():
    users = DEFAULT_USERS.copy()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                users.update(json.load(f))
        except Exception:
            pass
    # Optional: integrate with external client loader if exists
    try:
        from clients import load_all_clients
        users.update(load_all_clients())
    except Exception:
        pass
    return users

def save_users(u):
    with open(USERS_FILE, "w") as f:
        json.dump(u, f, indent=2)

def hash_pw(pw): 
    return hashlib.sha256(pw.encode()).hexdigest()

def verify_pw(pw, h): 
    return hash_pw(pw) == h

# ── AUTH STATE ──
if "logged_in" not in st.session_state:
    st.session_state.update({"logged_in": False, "client_name": "", "username": ""})

# ── AUTH PAGES ──
if not st.session_state["logged_in"]:
    st.markdown("<br>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("## 📉 Churn Predictor")
        st.caption("E-Commerce ML Dashboard")
        st.divider()
        tab_in, tab_up = st.tabs(["🔐 Sign In", "✍️ Sign Up"])
        
        with tab_in:
            st.markdown("#### Welcome back")
            u = st.text_input("Username", key="li_u")
            p = st.text_input("Password", type="password", key="li_p")
            if st.button("Sign In", use_container_width=True, type="primary"):
                users = load_users()
                if u in users and verify_pw(p, users[u]["password_hash"]):
                    st.session_state.update({
                        "logged_in": True, 
                        "client_name": users[u]["name"], 
                        "username": u
                    })
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
            st.caption("Demo: username `demo_client` / password `demo123`")
        
        with tab_up:
            st.markdown("#### Create your account")
            nm = st.text_input("Full Name", key="su_n")
            un = st.text_input("Choose a Username", key="su_u")
            pw = st.text_input("Password (min 6 chars)", type="password", key="su_p")
            pw2 = st.text_input("Confirm Password", type="password", key="su_p2")
            if st.button("Create Account", use_container_width=True, type="primary"):
                users = load_users()
                if not nm or not un or not pw:
                    st.error("Please fill in all fields.")
                elif pw != pw2:
                    st.error("Passwords do not match.")
                elif len(pw) < 6:
                    st.error("Password must be at least 6 characters.")
                elif un in users:
                    st.error("Username already taken.")
                else:
                    users[un] = {"password_hash": hash_pw(pw), "name": nm, "role": "client"}
                    save_users(users)
                    st.success(f"Account created! Please sign in, {nm}.")
    st.stop()

# ── MODEL CACHE ──
@st.cache_resource(show_spinner="Training on demo data …")
def get_demo_model():
    df = generate_synthetic_ecommerce_data(n=3000)
    m, a = train_model(df)
    return df, m, a

@st.cache_resource(show_spinner="Training on real Olist data … (~30 sec)")
def get_olist_model(cache_key, tmpdir):
    df = load_olist_data(tmpdir)
    m, a = train_model(df)
    return df, m, a

# ── SIDEBAR ──
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/graph-report.png", width=60)
    st.title("Churn Predictor")
    st.caption("E-Commerce ML Dashboard")
    st.divider()
    st.markdown(f"👋 Welcome, **{st.session_state['client_name']}**")
    if st.button("🚪 Logout"):
        st.session_state.update({"logged_in": False, "client_name": "", "username": ""})
        st.rerun()
    st.divider()
    st.markdown("### 📂 Data Source")
    data_source = st.radio("", ["Use demo data", "Upload Olist CSVs", "Upload single CSV"], label_visibility="collapsed")
    
    uploaded_file = None
    olist_files = {}
    
    if data_source == "Upload Olist CSVs":
        st.caption("Upload all 5 Olist CSV files:")
        for fname in [
            "olist_customers_dataset.csv",
            "olist_orders_dataset.csv",
            "olist_order_items_dataset.csv",
            "olist_order_payments_dataset.csv",
            "olist_order_reviews_dataset.csv"
        ]:
            f = st.file_uploader(fname, type=["csv"], key=fname)
            if f:
                olist_files[fname] = f
        n = len(olist_files)
        if n < 5:
            st.info(f"{n}/5 files uploaded")
        else:
            st.success("All 5 files ready!")
    
    elif data_source == "Upload single CSV":
        uploaded_file = st.file_uploader("Upload customer CSV", type=["csv"])
    
    st.divider()
    st.markdown("### ⚙️ Prediction Threshold")
    threshold = st.slider("Churn probability cutoff", 0.1, 0.9, 0.5, 0.05)
    
    st.divider()
    st.info("Built with **XGBoost + SHAP**.\n\nPredicts which customers are likely to churn so you can take action early.")

# ── RESOLVE MODEL ──
if data_source == "Upload Olist CSVs" and len(olist_files) == 5:
    ck = str(sorted([(k, v.size) for k, v in olist_files.items()]))
    if st.session_state.get("olist_cache_key") != ck:
        td = tempfile.mkdtemp()
        for fn, fo in olist_files.items():
            fo.seek(0)
            with open(os.path.join(td, fn), "wb") as out:
                out.write(fo.read())
        st.session_state["olist_tmpdir"] = td
        st.session_state["olist_cache_key"] = ck
    df_full, metrics, artifacts = get_olist_model(ck, st.session_state["olist_tmpdir"])
else:
    df_full, metrics, artifacts = get_demo_model()

model = artifacts["model"]
explainer = artifacts["explainer"]
shap_vals = artifacts["shap_values"]
X_test = artifacts["X_test"]

# ── HEADER ──
st.markdown("# 📉 E-Commerce Churn Prediction Dashboard")
st.markdown("Identify at-risk customers before they leave — powered by XGBoost & SHAP explainability.")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Overview",
    "👥 Customer Risk Table",
    "📊 Model Performance",
    "🔍 SHAP Explainability"
])

with tab1:
    if data_source == "Upload Olist CSVs" and len(olist_files) == 5:
        df_pred = df_full.drop(columns=["churn"], errors="ignore")
        st.success(f"Model retrained on {len(df_pred):,} real Olist customers ✅")
    elif data_source == "Upload Olist CSVs":
        st.warning(f"Please upload all 5 Olist CSV files ({len(olist_files)}/5 uploaded).")
        df_pred = df_full.drop(columns=["churn"], errors="ignore")
    elif data_source == "Upload single CSV" and uploaded_file:
        try:
            uploaded_file.seek(0)
            df_raw = pd.read_csv(uploaded_file)
            df_pred = auto_convert_csv(df_raw)
            fmt = "Telco-style" if "tenure" in df_raw.columns else "Custom"
            st.success(f"Loaded {len(df_pred):,} customers from your file.")
            st.info(f"📋 Detected **{fmt}** CSV — columns mapped automatically.")
        except Exception as e:
            st.error(f"Error: {e}")
            df_pred = df_full.drop(columns=["churn"], errors="ignore")
    else:
        df_pred = df_full.drop(columns=["churn"], errors="ignore")

    results = predict_churn(model, df_pred)
    
    high   = (results["risk_label"] == "🔴 High").sum()
    medium = (results["risk_label"] == "🟡 Medium").sum()
    low    = (results["risk_label"] == "🟢 Low").sum()
    avg_p  = results["churn_probability"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, label, color in [
        (c1, len(results),         "Total Customers",   "#7c6af7"),
        (c2, high,                 "🔴 High Risk",       "#ff6b6b"),
        (c3, medium,               "🟡 Medium Risk",     "#ffd93d"),
        (c4, low,                  "🟢 Low Risk",         "#6bcb77"),
        (c5, f"{avg_p:.1%}",       "Avg Churn Prob",     "#7c6af7")
    ]:
        col.markdown(
            f'<div class="metric-card"><div class="metric-value" style="color:{color}">{val}</div><div class="metric-label">{label}</div></div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    cc, cp = st.columns(2)
    
    with cc:
        st.markdown('<div class="section-header">Churn Probability Distribution</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(6,3), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        ax.hist(results["churn_probability"], bins=40, color="#7c6af7", edgecolor="#1e1e2e", alpha=0.9)
        ax.axvline(threshold, color="#ff6b6b", linestyle="--", lw=1.5, label=f"Threshold ({threshold})")
        ax.set_xlabel("Churn Probability", color="white", fontsize=10)
        ax.set_ylabel("# Customers", color="white", fontsize=10)
        ax.tick_params(colors="white")
        for s in ax.spines.values(): s.set_edgecolor("#3a3a5c")
        ax.legend(facecolor="#2a2a3e", labelcolor="white", fontsize=9)
        st.pyplot(fig)
        plt.close(fig)

    with cp:
        st.markdown('<div class="section-header">Risk Segment Breakdown</div>', unsafe_allow_html=True)
        fig2, ax2 = plt.subplots(figsize=(4,3), facecolor="#1e1e2e")
        ax2.set_facecolor("#1e1e2e")
        _, _, autos = ax2.pie(
            [high, medium, low],
            labels=["High", "Medium", "Low"],
            colors=["#ff6b6b", "#ffd93d", "#6bcb77"],
            autopct="%1.1f%%",
            startangle=140,
            textprops={"color": "white", "fontsize": 10}
        )
        for a in autos: a.set_color("black")
        st.pyplot(fig2)
        plt.close(fig2)

# (The rest of the tabs — Customer Risk Table, Model Performance, SHAP Explainability — remain unchanged)

with tab2:
    st.markdown('<div class="section-header">Customer Risk Scores</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    rf = f1.multiselect("Risk Level", ["🔴 High", "🟡 Medium", "🟢 Low"], default=["🔴 High", "🟡 Medium"])
    mp = f2.slider("Min probability", 0.0, 1.0, 0.0, 0.05)
    mr = f3.selectbox("Show rows", [25, 50, 100, 200], index=1)
    
    dc = [
        "customer_id", "churn_probability", "risk_label",
        "total_orders", "days_since_last_order", "avg_review_score",
        "support_tickets", "total_spend"
    ]
    
    filt = results[
        (results["risk_label"].isin(rf)) &
        (results["churn_probability"] >= mp)
    ].head(mr)
    
    st.dataframe(
        filt[dc].style
            .background_gradient(subset=["churn_probability"], cmap="RdYlGn_r")
            .format({"churn_probability": "{:.1%}", "total_spend": "${:,.0f}"}),
        use_container_width=True,
        height=450
    )
    
    st.download_button(
        "⬇️ Download Results CSV",
        data=filt[dc].to_csv(index=False).encode(),
        file_name="churn_predictions.csv",
        mime="text/csv"
    )

with tab3:
    st.markdown('<div class="section-header">Model Metrics</div>', unsafe_allow_html=True)
    m1, m2, m3, m4, m5 = st.columns(5)
    for col, key, label in [
        (m1, "auc",       "AUC-ROC"),
        (m2, "accuracy",  "Accuracy"),
        (m3, "precision", "Precision"),
        (m4, "recall",    "Recall"),
        (m5, "f1",        "F1-Score")
    ]:
        col.metric(label, f"{metrics[key]:.2%}")

    cr, cm2 = st.columns(2)
    with cr:
        st.markdown('<div class="section-header">ROC Curve</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(5,4), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        ax.plot(metrics["fpr"], metrics["tpr"], color="#7c6af7", lw=2, label=f'AUC = {metrics["auc"]:.3f}')
        ax.plot([0,1], [0,1], linestyle="--", color="#555", lw=1)
        ax.set_xlabel("False Positive Rate", color="white")
        ax.set_ylabel("True Positive Rate", color="white")
        ax.set_title("ROC Curve", color="white")
        ax.tick_params(colors="white")
        for s in ax.spines.values(): s.set_edgecolor("#3a3a5c")
        ax.legend(facecolor="#2a2a3e", labelcolor="white")
        st.pyplot(fig)
        plt.close(fig)

    with cm2:
        st.markdown('<div class="section-header">Confusion Matrix</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(4,4), facecolor="#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        cmat = metrics["cm"]
        im = ax.imshow(cmat, cmap="Purples")
        ax.set_xticks([0,1])
        ax.set_yticks([0,1])
        ax.set_xticklabels(["No Churn", "Churn"], color="white")
        ax.set_yticklabels(["No Churn", "Churn"], color="white")
        ax.set_xlabel("Predicted", color="white")
        ax.set_ylabel("Actual", color="white")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(cmat[i,j]), ha="center", va="center", color="white", fontsize=18, fontweight="bold")
        plt.colorbar(im, ax=ax)
        st.pyplot(fig)
        plt.close(fig)

with tab4:
    st.markdown('<div class="section-header">Feature Importance (SHAP)</div>', unsafe_allow_html=True)
    st.caption("SHAP explains *why* the model predicts churn for each customer.")
    cb, cs = st.columns(2)
    
    with cb:
        st.markdown("**Mean |SHAP| — Global Feature Impact**")
        fig, ax = plt.subplots(figsize=(6,5), facecolor="#1e1e2e")
        ax.set_facecolor("#3f3f61")
        ms = np.abs(shap_vals).mean(axis=0)
        o = np.argsort(ms)
        ax.barh(np.array(FEATURE_COLS)[o], ms[o], color=plt.cm.RdPu(np.linspace(0.3, 0.9, len(FEATURE_COLS))))
        ax.tick_params(colors="white", labelsize=8)
        ax.set_xlabel("Mean |SHAP value|", color="white")
        for s in ax.spines.values(): s.set_edgecolor("#3a3a5c")
        st.pyplot(fig)
        plt.close(fig)

    with cs:
        st.markdown("**SHAP Summary — Impact Direction**")
        shap.summary_plot(shap_vals, X_test, plot_type="dot", show=False, color_bar=True)
        fig = plt.gcf()
        fig.set_facecolor("#3f3f61")
        st.pyplot(fig)
        plt.close(fig)

    st.divider()
    st.markdown('<div class="section-header">🔎 Explain a Single Customer</div>', unsafe_allow_html=True)
    idx = st.slider("Select customer index", 0, len(X_test)-1, 0)
    shap.waterfall_plot(
        shap.Explanation(
            values=shap_vals[idx],
            base_values=explainer.expected_value,
            data=X_test.iloc[idx].values,
            feature_names=FEATURE_COLS
        ),
        show=False
    )
    fig = plt.gcf()
    fig.set_facecolor("#3f3f61")
    st.pyplot(fig)
    plt.close(fig)

st.divider()
st.caption("Built with XGBoost · SHAP · Streamlit · Pandas · Scikit-learn | Portfolio project")
