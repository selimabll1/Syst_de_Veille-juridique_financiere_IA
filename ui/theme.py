"""The sole injected stylesheet for the final UI.

Native widget colours are supplied by .streamlit/config.toml. No legacy theme
is loaded, and no !important cascade is needed.
"""
import streamlit as st

CSS = """
<style>
:root{--ug-bg:#031727;--ug-panel:#052036;--ug-edge:#123a55;--ug-text:#e4efff;--ug-muted:#86a9cf;--ug-blue:#17a9ff}
.stApp{background:radial-gradient(ellipse at 90% 0%,#061e31 0%,var(--ug-bg) 65%);color:var(--ug-text)}
[data-testid="stHeader"]{background:transparent;height:0;pointer-events:none}
[data-testid="stHeader"] [data-testid="stExpandSidebarButton"]{pointer-events:auto}
[data-testid="stToolbar"]{pointer-events:none}
[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"]{display:none}
[data-testid="stMainBlockContainer"]{padding:1rem 1.55rem 1.1rem;max-width:2400px}
[data-testid="stVerticalBlock"]{gap:.5rem}
.stApp [data-testid="stMarkdownContainer"]:has(>[class^="ug-"]),.stApp [data-testid="stMarkdownContainer"]:has(>[class^="f-"]){margin-bottom:0}
[data-testid="stSidebar"]{width:205px;min-width:205px;max-width:205px;background:linear-gradient(160deg,#04243d,#031727 55%);border-right:1px solid var(--ug-edge)}
[data-testid="stSidebarContent"]{padding-top:0}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{height:22px;min-height:22px;padding:0}
[data-testid="stSidebarUserContent"]{padding:.75rem .65rem}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.18rem}
[data-testid="stSidebar"] button{font-size:.76rem;justify-content:flex-start;min-height:2.15rem;text-align:left}
[data-testid="stSidebar"] button>div{justify-content:flex-start}
[data-testid="stSidebar"] button p{font-size:.76rem;line-height:1.3}
[data-testid="stSidebar"] button[kind="tertiary"]{color:#d5e5ff;padding:.4rem .65rem}
[data-testid="stSidebar"] button[kind="primary"]{background:linear-gradient(110deg,#078cff,#004ec1);border:1px solid #39adff;box-shadow:0 0 14px #0059aa30}
.ug-brand{text-align:center;padding:.25rem 0 .8rem;border-bottom:1px solid var(--ug-edge);margin-bottom:.4rem}
.ug-logo-frame{display:block;width:100px;height:76px;overflow:hidden;margin:0 auto .5rem}.ug-brand img{height:110px;width:110px;max-width:none;object-fit:contain;transform:translate(-5px,-16px)}.ug-brand p{font-size:.73rem;line-height:1.45;color:var(--ug-muted);margin:0}
.ug-nav-group{font-size:.60rem;font-weight:650;letter-spacing:.09em;color:var(--ug-blue);padding:.35rem .4rem .1rem;border-top:1px solid var(--ug-edge);margin-top:.15rem;line-height:1.5}
.ug-profile{border:1px solid var(--ug-edge);border-radius:8px;margin-top:1.3rem;padding:.7rem;display:flex;gap:.5rem;align-items:center;font-size:.7rem}
.ug-avatar{display:inline-grid;place-items:center;border:1px solid #135180;border-radius:50%;height:34px;width:34px;background:#08325a;color:#fff;font-size:.75rem;font-weight:600;flex-shrink:0}
.ug-profile small{display:block;color:var(--ug-muted);margin-top:.15rem}
.st-key-topbar{padding-bottom:.65rem;border-bottom:1px solid var(--ug-edge);margin-bottom:.1rem}
.ug-sync{font-size:.65rem;color:var(--ug-muted);padding:.22rem 0}.ug-sync strong{display:block;color:#cfdef4;font-weight:400;margin-top:.15rem;font-size:.65rem}
.st-key-kpis [data-testid="stHorizontalBlock"]{gap:.55rem}
.ug-kpi{border:1px solid #103853;border-radius:8px;background:linear-gradient(135deg,#082b46,#041d31);padding:.75rem;display:flex;gap:.75rem;align-items:center;min-height:84px}
.ug-kpi-icon{width:45px;height:45px;border-radius:50%;background:#0b3d69;color:#2fb7ff;display:grid;place-items:center;font-size:1.4rem;flex-shrink:0}
.ug-kpi-icon.purple{background:#25245c;color:#b18cff}.ug-kpi-icon.red{background:#44233b;color:#ff5874}.ug-kpi-icon.amber{background:#393631;color:#ffb65a}
.ug-kpi strong{font-size:1.2rem;line-height:1.2;display:block;color:#fff}.ug-kpi span{font-size:.70rem;display:block;margin-top:.18rem}.ug-kpi small{font-size:.62rem;color:var(--ug-muted);display:block;margin-top:.25rem}
.stApp [data-testid="stMarkdownContainer"] h1{font-size:1.45rem;font-weight:700;padding:.1rem 0;margin:0;line-height:1.35}.ug-subtitle{font-size:.75rem;color:var(--ug-muted);margin:.05rem 0 .45rem}
.stApp [data-testid="stMarkdownContainer"] h2{font-size:1.2rem}.stApp [data-testid="stMarkdownContainer"] h3{font-size:1.05rem}
[data-testid="stWidgetLabel"] p{font-size:.65rem;color:var(--ug-muted)}
[data-testid="stTextInput"] input{font-size:.75rem}
[data-baseweb="select"]{font-size:.73rem}
button[kind="secondary"],button[kind="primary"]{font-size:.73rem;min-height:2.1rem;border-radius:6px}
.stApp button p{font-size:.73rem;line-height:1.35}
button[kind="secondary"]{background:#062844;border:1px solid #155481;color:#cee4ff}
button[kind="secondary"]:hover{border-color:#2cafff;background:#093553;color:#fff}
button[kind="primary"]{background:linear-gradient(110deg,#078cff,#0060d8);border:1px solid #2baeff}
[data-testid="stPopover"] button{font-size:.75rem}
[data-testid="stHorizontalBlock"]{gap:.65rem}
[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--ug-edge)}
.st-key-main_filters{padding:.5rem .6rem;border:1px solid var(--ug-edge);border-radius:7px;background:#041e32}
[class*="st-key-alertrow_"]{border-bottom:1px solid #12334c;padding:.45rem .25rem .3rem;border-radius:3px}
[class*="st-key-alertrow_selected_"]{background:linear-gradient(100deg,#073763,#062139);border:1px solid #117cc1;border-left:3px solid var(--ug-blue);border-radius:6px}
[class*="st-key-alertrow_"] button[kind="tertiary"]{padding:0;min-height:1.45rem;justify-content:flex-start;text-align:left;line-height:1.3;font-size:.75rem;font-weight:600;color:#e4efff}
[class*="st-key-alertrow_"] button>div{justify-content:flex-start}
[class*="st-key-alertrow_"] button p{font-size:.74rem}
[class*="st-key-alertrow_"] [data-testid="stVerticalBlock"]{gap:.05rem}
.ug-rowmeta{font-size:.63rem;color:var(--ug-muted);display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;line-height:1.5}
.ug-row-source{color:#27aeff;font-size:.62rem;margin-top:.15rem}.ug-row-icon{width:30px;height:32px;border-radius:6px;background:#0b3861;color:#76c5ff;display:grid;place-items:center;font-size:1rem}
.ug-row-icon.cmf{background:#422739;color:#fb617c}
.ug-list-count{font-size:.68rem;color:var(--ug-muted);padding:.5rem 0}
.ug-reading{font-size:.60rem;color:#56baff;line-height:2.2}
.ug-rowbadges{display:flex;flex-wrap:wrap;align-items:center;gap:.12rem}.ug-rowbadges .ug-reading{width:100%}
[data-testid="stButtonGroup"] button p{font-size:.62rem}
.st-key-notification_detail{border:1px solid #123d5a;border-radius:8px;background:#041e31;padding:.7rem;position:sticky;top:.7rem}
.ug-detail-title{font-size:1rem;font-weight:700;color:#f1f4ff;line-height:1.35;margin:.15rem 0 .3rem}.ug-detail-subtitle{font-size:.7rem;color:#8cb8e9}
.f-info-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:.5rem}
.f-card,.f-result{border:1px solid #113a55;background:linear-gradient(120deg,#05263e,#041e32);border-radius:7px;padding:.65rem}
.f-card-title{font-size:.77rem;font-weight:650;color:#e8efff;margin-bottom:.4rem}
.f-kv{display:grid;grid-template-columns:1.04fr 1fr;gap:.5rem;padding:.25rem 0;font-size:.69rem;line-height:1.4}
.f-k{color:var(--ug-muted)}.f-v{color:#dfeaff;overflow-wrap:anywhere}.f-company{font-size:.83rem;font-weight:650;margin-bottom:.5rem}
.f-company-button{font-size:.63rem;border-top:1px solid var(--ug-edge);padding-top:.5rem;margin-top:.4rem;color:var(--ug-muted)}
.f-badge{display:inline-block;border:1px solid #175080;border-radius:5px;font-size:.62rem;padding:.14rem .43rem;white-space:nowrap;line-height:1.3;margin:.08rem .08rem .08rem 0;color:#8fd4ff;background:#073154}
.f-badge.high,.f-badge.critical,.f-badge.error{background:#3d2236;color:#ff657d;border-color:#8b344b}
.f-badge.medium,.f-badge.waiting{color:#ffbb64;background:#3b3126;border-color:#6d5031}
.f-badge.low,.f-badge.success{color:#37e1c2;background:#063b3b;border-color:#0e6a62}
.f-badge.service{background:#1c285e;border-color:#343d86;color:#b8b9ff}.f-badge.muted{color:#95acc8;background:#122a3e;border-color:#23425a}
.f-badge.purple,.f-badge.indigo{background:#1c285e;border-color:#343d86;color:#b8b9ff}.f-badge.cyan{background:#063344;border-color:#185471;color:#a5d8ed}
.f-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:currentColor;margin-right:.3rem;vertical-align:middle}
.f-reading{font-size:.65rem;color:#73bfff}.f-reading.read{color:#8fa9c6}
.f-summary{font-size:.74rem;color:#a9c8ee;line-height:1.55;overflow-wrap:anywhere;white-space:pre-wrap}
.f-results{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}.f-results.one{grid-template-columns:1fr}
.f-result-head{display:flex;justify-content:space-between;gap:.3rem;align-items:center}.f-result-name{font-size:.76rem;font-weight:600}.f-result-text{font-size:.71rem;color:#a9c8ee;line-height:1.5;margin-top:.4rem}
.f-meta,.f-empty{font-size:.72rem;color:var(--ug-muted);padding:.5rem 0}
.f-meta-row{display:grid;grid-template-columns:1fr 1.4fr;gap:.75rem;padding:.4rem 0;border-bottom:1px solid #10344b;font-size:.71rem}.f-meta-key{color:var(--ug-muted)}.f-meta-val{overflow-wrap:anywhere}
[data-baseweb="tab-list"]{gap:.75rem;background:transparent;border-bottom:1px solid #123750}
button[data-baseweb="tab"]{font-size:.71rem;height:2.2rem;padding:0 .1rem;color:#8db5e5}
button[data-baseweb="tab"][aria-selected="true"]{color:#21b1ff}
[data-baseweb="tab-highlight"]{background:#15a5ff;height:3px}
[data-testid="stDialog"] [role="dialog"]{background:#062239;color:var(--ug-text);border:1px solid #195782;max-height:90vh;overflow:auto}
[data-testid="stDialog"] [data-testid="stVerticalBlock"]{gap:.75rem}
[data-testid="stExpander"] details{border-color:var(--ug-edge);background:#052137}
[data-testid="stCaptionContainer"]{color:var(--ug-muted);font-size:.7rem}
hr{border-color:var(--ug-edge);margin:.5rem 0}
@media(min-width:1250px){.st-key-master_columns>[data-testid="stVerticalBlock"]>[data-testid="stHorizontalBlock"]{align-items:flex-start}}
@media(max-width:1100px){[data-testid="stMainBlockContainer"]{padding:1rem}.ug-kpi{padding:.6rem;gap:.4rem}.ug-kpi-icon{width:32px;height:32px}.f-info-grid{grid-template-columns:1fr}.ug-kpi small{display:none}}
@media(max-width:1100px){.st-key-master_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-master_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%;min-width:100%;flex:1 1 100%}.st-key-notification_detail{position:static}}
@media(max-width:900px){[data-testid="stHeader"]{height:2.7rem;background:var(--ug-bg)}[data-testid="stMainBlockContainer"]{padding-top:3rem}}
@media(max-width:800px){.st-key-notification_detail{position:static}.f-info-grid,.f-results{grid-template-columns:1fr}.ug-kpi{min-height:70px}.ug-kpi strong{font-size:1rem}}
.ug-status-stack{display:grid;grid-template-columns:auto 1fr;gap:5px 8px;align-items:center;min-width:155px;padding:5px 0}
.ug-status-stack>span:nth-child(odd){font-size:10px;color:#8ba9bf;font-weight:500}
.ug-status-stack .f-badge{justify-self:start;margin:0;font-size:10px;white-space:nowrap}
.ug-status-stack .f-reading{font-size:11px;padding-left:5px}
.ug-status-stack .f-badge.waiting{background:#083455;color:#9bcaff;border:1px solid #195176}
.ug-admin-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0 16px}
.ug-admin-kpi{border:1px solid var(--ug-edge);background:linear-gradient(130deg,#05263d,#031b2d);border-radius:9px;padding:15px;display:flex;flex-direction:column;gap:5px}
.ug-admin-kpi strong{font-size:1.4rem;color:#e4efff}.ug-admin-kpi small{color:#8dd2f2;font-size:.78rem}.ug-admin-kpi span{color:var(--ug-muted);font-size:.7rem}
.ug-admin-question{font-size:16px;font-weight:650;color:#eaf5ff;margin:8px 0 4px}
.st-key-admin_simplified_cards [data-testid="stHorizontalBlock"]{gap:10px}
.st-key-admin_simplified_cards [data-testid="stColumn"]{min-width:170px;flex:1 1 170px}
.ug-admin-simple-card{display:flex;flex-direction:column;gap:5px;min-height:78px;padding:2px 0 8px}.ug-admin-simple-card strong{font-size:15px;color:#f0f7ff}.ug-admin-simple-card span{font-size:11px;color:#9fc1d8;line-height:1.35}.ug-admin-simple-card b{font-size:12px;color:#72d4e8;font-weight:600}
.ug-admin-empty-reference{border:1px solid #1a5273;border-radius:12px;background:linear-gradient(130deg,#062b43,#041d30);padding:30px 28px;margin:12px 0 14px;text-align:center}.ug-admin-empty-icon{display:grid;place-items:center;width:48px;height:48px;margin:0 auto 10px;border-radius:50%;background:#0b4162;color:#76d7f4;font-size:28px}.ug-admin-empty-reference h2{font-size:22px;margin:0 0 8px;color:#f0f7ff}.ug-admin-empty-reference p{max-width:680px;margin:0 auto;color:#a8c7da;font-size:13px;line-height:1.55}
.ug-admin-reference-intro{display:flex;justify-content:space-between;align-items:center;border:1px solid #164766;border-radius:8px;background:#06253a;padding:11px 14px;margin:10px 0}.ug-admin-reference-intro strong{color:#eaf5ff}.ug-admin-reference-intro span{font-size:11px;color:#9fc1d8}
.ug-admin-health-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}.ug-admin-health{display:flex;justify-content:space-between;align-items:center;gap:12px;border:1px solid #16445f;border-radius:9px;background:linear-gradient(130deg,#06283e,#041d30);padding:13px 14px}.ug-admin-health strong{display:block;color:#ecf6ff;font-size:13px}.ug-admin-health span{display:block;color:#9fc1d8;font-size:11px;margin-top:4px}.ug-admin-health b{font-size:11px;white-space:nowrap;color:#65d6b0}.ug-admin-health.warn b{color:#f4c879}.ug-admin-health.neutral b{color:#a9bbca}
@media(max-width:800px){.ug-admin-health-grid{grid-template-columns:1fr}.ug-admin-reference-intro{display:block}.ug-admin-reference-intro span{display:block;margin-top:4px}}

.st-key-admin_service_cards [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
.st-key-admin_service_cards [data-testid="stColumn"]{min-width:145px;flex:1 1 145px}
@media(max-width:1100px){.st-key-admin_overview_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-admin_overview_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%;min-width:100%;flex:1 1 100%}}

/* Accueil: scoped dashboard composition; sidebar/topbar remain unchanged. */
.st-key-home_dashboard{--home-edge:#12435f;--home-meta:#a2c4dd}
.st-key-home_dashboard [data-testid="stVerticalBlock"]{gap:12px}
.ug-home-hero{display:flex;align-items:center;justify-content:space-between;position:relative;overflow:hidden;min-height:94px;padding:5px 2px 12px}
.ug-home-hero h1{font-size:36px;line-height:1.15;margin:0 0 7px;letter-spacing:-.6px;font-weight:700;color:#f4f8fb;padding:0}
.ug-home-hero p{font-size:15px;margin:0;color:#aecde2}.ug-home-hero>div{z-index:1}
.ug-home-hero>svg{position:absolute;right:19%;top:-22px;width:430px;height:160px;opacity:.2;pointer-events:none}
.ug-home-hero aside{font-size:13px;line-height:1.5;padding:5px 12px 5px 20px;border-left:2px solid #1b78a8;color:#b4d5e9;z-index:1}
.st-key-home_dashboard .st-key-kpis{margin:0 0 2px}
.st-key-home_dashboard .ug-kpi{height:108px;padding:16px 14px;border-radius:11px;gap:12px;border-color:var(--home-edge);background:linear-gradient(130deg,#06283e,#041d30);box-shadow:none}
.st-key-home_dashboard .ug-kpi strong{font-size:26px;line-height:1.2}.st-key-home_dashboard .ug-kpi span{font-size:12px;margin-top:4px}.st-key-home_dashboard .ug-kpi small{font-size:11px;color:var(--home-meta);margin-top:7px;display:block}
.st-key-home_dashboard .ug-kpi-icon{width:47px;height:47px;flex-shrink:0}
.st-key-home_activity,.st-key-home_feed,.st-key-home_attention,.st-key-home_sources,.st-key-home_reference{border:1px solid var(--home-edge);background:linear-gradient(125deg,#062337,#041b2d);border-radius:11px;padding:14px 15px}
.ug-home-panelhead{display:flex;align-items:center;gap:10px;min-height:38px}.ug-home-panelhead h2{font-size:17px;line-height:1.25;margin:0;padding:0;color:#f4f8fb;font-weight:650}.ug-home-panelhead p{font-size:11px;color:var(--home-meta);margin:3px 0 0}
.ug-home-icon{display:inline-flex;align-items:center;justify-content:center;background:#0a304d;color:#71c9ff;width:36px;height:36px;border-radius:50%;flex-shrink:0}.ug-home-icon svg{width:21px;height:21px}
.st-key-home_dashboard button p{font-size:11px}.st-key-home_dashboard button{min-height:32px;border-radius:6px}
.ug-home-service{display:flex;gap:12px;align-items:center;min-height:118px;padding:13px 12px;border:1px solid #164261;border-radius:9px;background:linear-gradient(130deg,#0a304b,#06233a)}
.ug-home-orb{width:45px;height:45px;border-radius:50%;display:grid;place-items:center;flex-shrink:0;background:#0a4761;color:#66d4f6}.ug-home-orb.purple{background:#33265c;color:#ba9bec}.ug-home-orb.blue{background:#123e75;color:#8fc8ff}.ug-home-orb.amber{background:#594429;color:#f3ce8f}
.ug-home-service h3{font-size:14px;font-weight:650;margin:0 0 5px;padding:0;line-height:1.2}.ug-home-count{font-size:12px;color:#bdd5e5}.ug-home-count strong{font-size:24px;line-height:1;margin-right:4px;color:#f4f8fb}.ug-home-service small{display:block;font-size:10px;color:#b0cbdc;margin-top:6px}.ug-home-service p{font-size:10px;color:#99bed6;margin:5px 0 0;line-height:1.4}.ug-home-chevron{margin-left:auto;color:#83bde6;display:flex;flex-shrink:0}.ug-home-chevron svg{width:16px}
[class*="st-key-home_service_"],[class*="st-key-home_feedrow_"],[class*="st-key-home_reviewrow_"]{position:relative}
[class*="st-key-home_service_"] [data-testid="stElementContainer"]:has(button),[class*="st-key-home_feedrow_"] [data-testid="stElementContainer"]:has(button),[class*="st-key-home_reviewrow_"] [data-testid="stElementContainer"]:has(button){position:absolute;inset:0;z-index:2}
[class*="st-key-home_service_"] [data-testid="stButton"],[class*="st-key-home_feedrow_"] [data-testid="stButton"],[class*="st-key-home_reviewrow_"] [data-testid="stButton"]{height:100%;width:100%}
[class*="st-key-home_service_"] button,[class*="st-key-home_feedrow_"] button,[class*="st-key-home_reviewrow_"] button{opacity:0;height:100%;width:100%;cursor:pointer}
[class*="st-key-home_service_"]:hover .ug-home-service,[class*="st-key-home_service_"]:focus-within .ug-home-service{border-color:#35a1cf;background:#0a3049}
[class*="st-key-home_feedrow_"]:hover,[class*="st-key-home_feedrow_"]:focus-within,[class*="st-key-home_reviewrow_"]:hover,[class*="st-key-home_reviewrow_"]:focus-within{background:#0b2c43;outline:1px solid #1b78a8;border-radius:7px}
.ug-home-feedrow{display:flex;align-items:center;gap:11px;padding:9px 0;border-bottom:1px solid #12374f;min-height:70px}.ug-home-feedrow>.ug-home-icon{border-radius:9px;width:32px;height:32px}.ug-home-feedtext{min-width:0;flex:1}.ug-home-feedtext>strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600}.ug-home-feedtext>small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--home-meta);font-size:10px;margin:3px 0}.ug-home-feedtext .f-badge{font-size:9px;padding:2px 5px}.ug-home-feedmeta{display:flex;align-items:flex-end;flex-direction:column;gap:4px;min-width:105px}.ug-home-feedmeta small,.ug-home-feedmeta time{font-size:10px;color:var(--home-meta)}
.ug-home-attention-count{font-size:12px;color:#b4cddd;margin:1px 0 4px}.ug-home-attention-count strong{font-size:32px;color:#f4f8fb;margin-right:7px}
.ug-home-review{display:flex;align-items:center;gap:10px;border:1px solid #123f5c;border-radius:8px;background:#08273e;padding:9px;min-height:56px}.ug-home-review>div{flex:1;min-width:0}.ug-home-review strong{font-size:11px;display:block;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.ug-home-review small{font-size:10px;color:var(--home-meta);display:block;margin-top:4px}.ug-home-review>svg{width:16px;flex-shrink:0;color:#8bbfdd}
.ug-home-source{padding:9px 0;border-bottom:1px solid #12374f}.ug-home-source>div{display:flex;align-items:center;justify-content:space-between;gap:12px}.ug-home-source strong{font-size:12px}.ug-home-source-state{font-size:10px;color:#83d7ee;text-align:right}.ug-home-source-state.amber{color:#efc782}.ug-home-source small{display:block;font-size:10px;color:var(--home-meta);margin-top:6px}
.ug-home-reference{border:1px solid #174463;border-radius:8px;background:#08283f;padding:12px}.ug-home-reference strong{font-size:12px}.ug-home-reference p{font-size:11px;line-height:1.5;color:var(--home-meta);margin:7px 0 0}.ug-home-empty{padding:15px 8px;color:#aecddb;font-size:12px}
.st-key-home_dashboard [data-testid="stHorizontalBlock"]{gap:12px}
@media(min-width:1100px){.st-key-home_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:first-child{flex:1.85 1 0;min-width:0}.st-key-home_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:last-child{flex:1 1 0;min-width:0}}
@media(max-width:1200px){.ug-home-hero aside{display:none}.ug-home-hero>svg{right:0}.st-key-home_dashboard .ug-kpi{padding:12px 9px;gap:8px}.st-key-home_dashboard .ug-kpi-icon{width:34px;height:34px}.st-key-home_dashboard .ug-kpi span{font-size:11px}.ug-home-orb{width:34px;height:34px}.ug-home-service{gap:8px;padding:11px 8px}.ug-home-service p{display:none}.ug-home-feedmeta{min-width:80px}}
@media(max-width:950px){.st-key-home_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-home_columns>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%;min-width:100%;flex:1 1 100%}.ug-home-hero h1{font-size:30px}}
@media(max-width:650px){.ug-home-hero p{font-size:12px}.st-key-home_dashboard .st-key-kpis [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-home_dashboard .st-key-kpis [data-testid="stColumn"]{min-width:130px;flex:1 1 130px}.ug-home-feedmeta{min-width:60px}.ug-home-service small{font-size:9px}}
.st-key-operation_notice [data-testid="stHorizontalBlock"]{align-items:center}.st-key-operation_notice{border:1px solid #17435e;border-radius:7px;padding:4px 10px;background:#06253a}.st-key-operation_notice p{font-size:12px}


.stApp .st-key-home_dashboard [data-testid="stMarkdownContainer"] h1{font-size:36px;line-height:1.15;margin:0 0 7px;padding:0}
.stApp .st-key-home_dashboard [data-testid="stMarkdownContainer"] h2{font-size:17px;line-height:1.25}
.stApp .st-key-home_dashboard [data-testid="stMarkdownContainer"] h3{font-size:14px;line-height:1.2}
.ug-home-service{min-height:98px}.ug-home-feedtext>small{display:inline-block;max-width:55%;vertical-align:middle}.ug-home-feedtext>div{display:inline-block;margin-left:6px;vertical-align:middle}
.st-key-home_feed [data-testid="stVerticalBlock"]{gap:4px}
@media(max-width:950px){.stApp .st-key-home_dashboard [data-testid="stMarkdownContainer"] h1{font-size:30px}}

.st-key-home_dashboard [data-testid="stVerticalBlock"]{gap:10px}
.st-key-home_activity,.st-key-home_feed,.st-key-home_attention,.st-key-home_sources,.st-key-home_reference{padding:12px 14px}
.stApp .st-key-home_dashboard .ug-home-service h3{margin:0;font-size:14px}
.ug-home-service{padding:10px 12px;min-height:98px}.ug-home-count{line-height:1.1;margin-top:3px}.ug-home-count strong{font-size:24px}.ug-home-service small{line-height:1.2;margin-top:3px}.ug-home-service p{line-height:1.2;margin-top:3px}
.ug-home-attention-count{line-height:1.15;margin:0}.ug-home-attention-count strong{line-height:1.15}
.ug-home-review{min-height:48px;padding:7px 9px}
.ug-home-source{padding:7px 0}.ug-home-source small{margin-top:3px;line-height:1.25}
.ug-home-feedrow{min-height:60px;padding:7px 0}.ug-home-feedmeta{display:grid;grid-template-columns:auto auto;gap:4px 8px;align-items:center}.ug-home-feedmeta>.f-badge{grid-column:1/-1;justify-self:end}.ug-home-feedmeta time{white-space:nowrap}
.st-key-home_feed [data-testid="stVerticalBlock"]{gap:3px}
/* Final workflow workspaces and non-blocking action center. */
.st-key-action_center{position:fixed;right:24px;top:88px;width:min(510px,calc(100vw - 40px));max-height:65vh;overflow:auto;z-index:990;background:#102e49;border:1px solid #35b7e6;border-radius:12px;padding:12px 14px;box-shadow:0 12px 40px #00101de0,0 0 18px #35b7e61c}
.st-key-action_center [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:8px}.st-key-action_center [data-testid="stColumn"]{min-width:80px}
.ug-action-stage{font-size:12px;padding:3px 0;color:#abc5d9}.ug-action-stage.active{color:#75d5fa;animation:ug-pulse 1.5s ease-in-out infinite}
@keyframes ug-pulse{50%{opacity:.5}}
.ug-timeline-event{display:flex;gap:20px;border-left:2px solid #1b78a8;padding:12px 20px;margin-left:8px;background:linear-gradient(90deg,#0a293e,#061b2d);border-bottom:1px solid #13364d}
.ug-timeline-event time{font-size:12px;color:#72ccee;min-width:40px}.ug-timeline-event strong{font-size:14px;color:#f4f8fb}.ug-timeline-event p{font-size:12px;color:#bbd2df;margin:5px 0}.ug-timeline-event small{color:#6eb0d6}
[data-testid="stMetricValue"]{font-size:1.25rem}
@media(max-width:1100px){.st-key-master_columns [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-main_filters [data-testid="stColumn"]{min-width:120px;flex:1 1 120px}}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)
