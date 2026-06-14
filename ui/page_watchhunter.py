"""Page WatchHunter : opportunités montres d'occasion."""

import streamlit as st
import pandas as pd
import glob
import os


WATCH_HUNTER_DIR = r"D:\Github\WatchHunter"
RUNS_LOG = r"D:\Github\WatchHunter\runs.csv"


def charger_opportunites() -> pd.DataFrame:
    """Charge et dédoublonne tous les CSV générés par WatchHunter."""
    fichiers = glob.glob(os.path.join(WATCH_HUNTER_DIR, "opportunites_*.csv"))
    if not fichiers:
        return pd.DataFrame()

    dfs = []
    for f in fichiers:
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # Dédoublonnage par URL
    combined = combined.drop_duplicates(subset=["url"], keep="last")

    # Trier par marge nette décroissante
    if "marge_nette" in combined.columns:
        combined = combined.sort_values("marge_nette", ascending=False)

    return combined.reset_index(drop=True)


def charger_historique() -> pd.DataFrame:
    try:
        df = pd.read_csv(RUNS_LOG, encoding="utf-8-sig")
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date", ascending=False)
    except Exception:
        return pd.DataFrame()


def render():
    st.title("🕐 WatchHunter")
    st.caption("Opportunités montres d'occasion — ACHETER & NÉGOCIER uniquement")

    # ── Historique des runs ───────────────────────────────────────────────────
    hist = charger_historique()
    if not hist.empty:
        with st.expander(f"📋 Historique — {len(hist)} run(s)", expanded=False):
            total_annonces = hist["nb_annonces"].sum()
            total_opps = hist["nb_opportunites"].sum()
            dernier_run = hist["date"].iloc[0].strftime("%d/%m/%Y %H:%M")

            c1, c2, c3 = st.columns(3)
            c1.metric("Dernier run", dernier_run)
            c2.metric("Annonces analysées", int(total_annonces))
            c3.metric("Opportunités trouvées", int(total_opps))

            st.dataframe(
                hist.rename(columns={"date": "Date", "nb_annonces": "Annonces", "nb_opportunites": "Opportunités"}),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("<div style='height:1px;background:#1e2d45;margin:1rem 0;'></div>", unsafe_allow_html=True)

    df = charger_opportunites()

    if df.empty:
        st.info("Aucune opportunité détectée pour l'instant. L'agent tourne toutes les heures.")
        st.caption(f"Dossier surveillé : `{WATCH_HUNTER_DIR}`")
        return

    # ── Métriques rapides ─────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Opportunités", len(df))
    with col2:
        n_acheter = len(df[df["verdict"] == "ACHETER"]) if "verdict" in df.columns else 0
        st.metric("ACHETER", n_acheter)
    with col3:
        n_nego = len(df[df["verdict"] == "NÉGOCIER"]) if "verdict" in df.columns else 0
        st.metric("NÉGOCIER", n_nego)
    with col4:
        marge_max = df["marge_nette"].max() if "marge_nette" in df.columns else 0
        st.metric("Meilleure marge", f"{marge_max:.0f} €")

    st.markdown("<div style='height:1px;background:#1e2d45;margin:1rem 0;'></div>", unsafe_allow_html=True)

    # ── Filtres ───────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        verdicts = df["verdict"].unique().tolist() if "verdict" in df.columns else []
        filtre_verdict = st.multiselect("Verdict", verdicts, default=verdicts)
    with col_f2:
        marge_min = st.slider("Marge nette minimum (€)", 0, 200, 0, step=5)

    df_filtre = df.copy()
    if filtre_verdict and "verdict" in df.columns:
        df_filtre = df_filtre[df_filtre["verdict"].isin(filtre_verdict)]
    if "marge_nette" in df.columns:
        df_filtre = df_filtre[df_filtre["marge_nette"] >= marge_min]

    st.caption(f"{len(df_filtre)} annonce(s) affichée(s)")

    # ── Tableau des opportunités ───────────────────────────────────────────────
    for _, row in df_filtre.iterrows():
        verdict = row.get("verdict", "?")
        emoji = "✅" if verdict == "ACHETER" else "🟡"
        marge = row.get("marge_nette", 0)
        marge_pct = row.get("marge_pct", 0)
        prix = row.get("prix", 0)
        prix_marche = row.get("prix_marche", 0)
        cote = row.get("cote", "?")
        commentaire = row.get("commentaire", "")
        url = row.get("url", "")
        titre = row.get("titre", "Sans titre")
        lieu = row.get("lieu", "")
        score = row.get("score", 0)

        with st.container():
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{emoji} {titre}**")
                st.caption(f"📍 {lieu} · Cote {cote}")
                if commentaire:
                    st.caption(f"💬 {commentaire}")
            with c2:
                st.markdown(f"**{prix} €** → marché ~{prix_marche} €")
                st.markdown(f"Marge nette : **{marge:.0f} € ({marge_pct:.0f}%)**")
                st.caption(f"Score : {score}/10")
            with c3:
                if url:
                    st.link_button("Voir l'annonce 🔗", url, use_container_width=True)
                st.caption(verdict)

        st.markdown("<div style='height:1px;background:#1e2d45;margin:0.5rem 0;'></div>", unsafe_allow_html=True)
