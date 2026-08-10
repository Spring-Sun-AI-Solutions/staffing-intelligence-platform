"""pages/8_rate_optimizer.py — Rate Optimizer"""
import streamlit as st

st.set_page_config(page_title="Rate Optimizer", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("💰 Rate Optimizer")
st.caption("Get recommended bill rate, pay rate, and margin for any skill and location.")

col1, col2 = st.columns(2)
with col1:
    skill    = st.text_input("Primary skill *", placeholder="e.g. Python, AWS, React")
    location = st.text_input("Location", value="Remote", placeholder="e.g. New York, NY")
with col2:
    visa = st.selectbox("Visa status", ["citizen","gc","h1b","opt","stem_opt","ead","unknown"])
    yoe  = st.number_input("Years of experience", min_value=0.0, max_value=30.0, value=5.0, step=0.5)

if st.button("💰 Get Recommendation", type="primary", disabled=not skill.strip()):
    from ml.forecaster import optimize_rate
    result = optimize_rate(skill=skill, location=location, visa=visa, yoe=yoe)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bill Rate",  f"${result['recommended_bill_rate']}/hr")
    col2.metric("Pay Rate",   f"${result['recommended_pay_rate']}/hr")
    col3.metric("Margin",     f"${result['recommended_margin']}/hr")
    col4.metric("Margin %",   f"{result['margin_pct']}%")

    st.info(
        f"📊 Market rate: **${result['market_rate']}/hr** | "
        f"Range: **${result['range']['min']}–${result['range']['max']}/hr**"
    )

    with st.expander("How this was calculated"):
        inputs = result["inputs"]
        st.write(f"- Skill: {inputs['skill']}")
        st.write(f"- Location multiplier applied for: {inputs['location']}")
        st.write(f"- Visa: {inputs['visa']}")
        st.write(f"- YOE adjustment for {inputs['yoe']} years")
        st.write(f"- Target margin: 25%")
