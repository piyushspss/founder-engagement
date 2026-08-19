"""Archetype labeller — PLAN §4.4.

**This module is a LABEL. It changes no number.** It reads a CanonicalProfile
and (read-only) the already-computed signals, and returns a name plus which
evidence to highlight and which evidence is conspicuously absent for that kind
of founder. Nothing here can move `broad_score`, `confidence`, an exceptional
flag, attention, potential or data_state — enforced by tests, and structurally
by the fact that this module returns a new object and mutates nothing.

Why a label is still worth having: "Clinical Expert, missing founder and
technical evidence" tells a human what question to ask next. A score of 58 does
not. The archetype selects the frame; the policy still decides the action.

Rules come from `config/archetypes.yaml` (evaluated in order, first match wins),
with the configured Hybrid behaviour when two or more archetypes are each
carried by a material share of the person's role-months.

**There are EIGHT archetypes** — Repeat Founder, Clinical Expert, Scientific
Expert, Healthcare Operator, Technical Builder, Product Builder, Commercial/GTM
and Hybrid. `Insufficient Evidence` (config `unknown_label`) is a separate
FALLBACK LABEL for a profile that matched no archetype, not a ninth archetype:
it names the absence of a label rather than a kind of founder, and no archetype
rule can produce it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evidence.progression import at_least, management_order
from app.evidence.signal import Signal, Strength
from app.models.canonical import CanonicalProfile, FounderTitleFlag, Ternary

# `missing_candidates` in config names some things that are not broad signals.
# They are resolved here against the canonical profile instead.
_TECH_DEPARTMENTS = {"engineering", "information technology", "data", "technology",
                     "architecture", "data science", "software"}


@dataclass
class ArchetypeResult:
    """`archetype` is the PRIMARY label — the one the UI leads with. Every
    archetype whose rules held is kept in `matched`, and the ones that are not
    primary are `secondary`. Nothing here is an input to any number."""

    archetype: str
    strong_signals: list[str] = field(default_factory=list)
    missing_for_archetype: list[str] = field(default_factory=list)
    explanation: str = ""
    matched: list[str] = field(default_factory=list)   # every archetype whose rules held
    secondary: list[str] = field(default_factory=list)  # matched, minus the primary
    shares: dict[str, float] = field(default_factory=dict)  # role-month share per match

    @property
    def primary_archetype(self) -> str:
        """Alias for `archetype`; the API serialises both names."""
        return self.archetype

    def to_dict(self) -> dict:
        """JSON form for the API. Purely descriptive — no field here is read by
        the scorer or the safety policy."""
        return {"primary_archetype": self.archetype, "archetype": self.archetype,
                "strong_signals": self.strong_signals,
                "missing_for_archetype": self.missing_for_archetype,
                "explanation": self.explanation, "matched": self.matched,
                "secondary": self.secondary,
                "shares": {k: round(v, 3) for k, v in self.shares.items()}}


# --------------------------------------------------------------------- helpers
def _dept(role) -> str:
    """Lower-cased department, or empty string when absent."""
    return (role.department or "").strip().lower()


def _months(role) -> int:
    """Role duration in months; an unknown duration counts as 0."""
    return role.duration_months or 0


def _total_months(profile: CanonicalProfile) -> int:
    """Total months across all roles."""
    return sum(_months(r) for r in profile.roles)


def _degrees(profile: CanonicalProfile) -> set[str]:
    """The set of degree types held."""
    return {e.degree_type.value for e in profile.education}


def _health_months(profile: CanonicalProfile) -> int:
    """Months spent in roles positively flagged healthcare."""
    return sum(_months(r) for r in profile.roles if r.health_flag is Ternary.YES)


def _roles_in_departments(profile: CanonicalProfile, names: list[str]) -> list:
    """Roles whose department matches any of `names`, case/space-insensitively."""
    wanted = {n.strip().lower() for n in names}
    return [r for r in profile.roles if _dept(r) in wanted]


# ------------------------------------------------------- requirement evaluation
def _check(profile: CanonicalProfile, requires: dict, cfg) -> tuple[bool, list[str], list]:
    """Evaluate one archetype's `requires` block.

    Returns (matched, reasons, attributable_roles). `attributable_roles` is the
    set of roles that actually carried the match — it is what the Hybrid
    role-month share is computed from, so a label can never be justified by
    evidence the label did not use."""
    reasons: list[str] = []
    attributable: list = []

    if requires.get("fallback"):
        return False, ["fallback archetype — never matched directly"], []

    if "explicit_founder_roles_min" in requires:
        founders = [r for r in profile.roles
                    if r.founder_title_flag is FounderTitleFlag.EXPLICIT]
        need = requires["explicit_founder_roles_min"]
        if len(founders) < need:
            return False, [f"explicit founder roles {len(founders)} < {need}"], []
        reasons.append(f"{len(founders)} explicit founder role(s) >= {need}")
        attributable += founders

    if "any_of" in requires:
        ok = False
        for clause in requires["any_of"]:
            for key, values in clause.items():
                if key.endswith("_degree_in"):
                    hit = _degrees(profile) & {v.upper() for v in values}
                    if hit:
                        ok = True
                        reasons.append(f"{key}: {sorted(hit)}")
                elif key.endswith("_department_in"):
                    roles = _roles_in_departments(profile, values)
                    if roles:
                        ok = True
                        reasons.append(
                            f"{key}: {sorted({r.department for r in roles})}")
                        attributable += roles
        if not ok:
            return False, [f"none of any_of satisfied: {requires['any_of']}"], []

    if "health_months_min" in requires:
        hm, need = _health_months(profile), requires["health_months_min"]
        if hm < need:
            return False, [f"health months {hm} < {need}"], []
        reasons.append(f"{hm} health months >= {need}")

    if "health_or_science_months_min" in requires:
        # No separate "science" industry taxonomy exists in the MVP config, so
        # this is evaluated on health months only, and that limitation is stated
        # rather than papered over with a guess about which industries count.
        hm, need = _health_months(profile), requires["health_or_science_months_min"]
        if hm < need:
            return False, [f"health/science months {hm} < {need} "
                           f"(evaluated on health months only — no science taxonomy in MVP config)"], []
        reasons.append(f"{hm} health/science months >= {need}")

    if "management_level_at_least" in requires:
        # CP4-R3: seniority gates use the ONE canonical ordering — the leadership
        # `level_scores` in config, where CP3 deliberately placed `Lead` (0.42)
        # BELOW `Manager` (0.45) because a Lead may be a senior IC or a function
        # lead rather than a people manager. The coarse step ladder used for
        # counting progression magnitude ties those two, and must never be used
        # to answer an "at least this senior" question.
        need_level = requires["management_level_at_least"]
        order = management_order(cfg)
        qualifying = [r for r in profile.roles
                      if at_least(r.management_level, need_level, cfg)]
        if not qualifying:
            known = [(order[r.management_level], r.management_level)
                     for r in profile.roles if r.management_level in order]
            got = max(known)[1] if known else "none recorded"
            return False, [f"highest management level {got!r} below {need_level!r}"], []
        best = max(qualifying, key=lambda r: order[r.management_level])
        reasons.append(f"reached {best.management_level!r} "
                       f"({order[best.management_level]} >= {need_level!r} "
                       f"{order[need_level]})")

    for key in ("department_in", "department_in_any"):
        if key in requires:
            roles = _roles_in_departments(profile, requires[key])
            if not roles:
                seen = sorted({r.department for r in profile.roles if r.department})
                return False, [f"no role in departments {requires[key]}; "
                               f"departments present: {seen or 'none recorded'}"], []
            reasons.append(f"{key}: {sorted({r.department for r in roles})}")
            attributable += roles

    return True, reasons, attributable


# ------------------------------------------------------------------- highlights
def _resolve_highlight(name: str, signals: dict[str, Signal],
                       profile: CanonicalProfile, exceptional_flag: bool) -> bool:
    """Is this highlight actually EVIDENCED? Used for both `strong_signals`
    (evidenced) and `missing_for_archetype` (not evidenced)."""
    if name in signals:
        s = signals[name]
        return s.observed and s.strength in (Strength.MEDIUM, Strength.STRONG)
    if name == "technical_evidence":
        return any(_dept(r) in _TECH_DEPARTMENTS for r in profile.roles)
    if name == "exceptional_signals":
        return exceptional_flag
    return False


def label_archetype(profile: CanonicalProfile, signals: list[Signal], cfg,
                    exceptional_flag: bool = False) -> ArchetypeResult:
    """Assign an archetype. `signals` is read only to decide which evidence to
    HIGHLIGHT; no signal value is read into any matching rule, and none is
    modified."""
    acfg = cfg.archetypes
    sig_map = {s.name: s for s in signals}
    total = _total_months(profile)

    matches: list[tuple[dict, list[str], list]] = []
    fail_reasons: dict[str, str] = {}
    for entry in acfg["archetypes"]:
        ok, reasons, attributable = _check(profile, entry.get("requires", {}), cfg)
        if ok:
            matches.append((entry, reasons, attributable))
        else:
            fail_reasons[entry["name"]] = "; ".join(reasons)

    if not matches:
        label = acfg["unknown_label"]
        return ArchetypeResult(
            archetype=label, strong_signals=[], missing_for_archetype=[],
            explanation=(f"{label}: no configured archetype's rules were satisfied. "
                         f"{acfg['unknown_note']} Nearest misses — "
                         + "; ".join(f"{k}: {v}" for k, v in list(fail_reasons.items())[:3])))

    # Hybrid: >= min_matching_archetypes matched AND each is carried by at least
    # min_role_month_share of the person's measured role-months. The share gate
    # is what stops a single incidental role from manufacturing a second label.
    hcfg = acfg["hybrid"]
    shares: dict[str, float] = {}
    for entry, _reasons, attributable in matches:
        months = sum(_months(r) for r in {id(r): r for r in attributable}.values())
        shares[entry["name"]] = (months / total) if total else 0.0

    material = [(e, r, a) for e, r, a in matches
                if shares.get(e["name"], 0.0) >= hcfg["min_role_month_share"]]

    hybrid_entry = next((e for e in acfg["archetypes"]
                         if e.get("requires", {}).get("fallback")), None)
    precedence = acfg.get("primary_precedence", [])
    matched_names = [e["name"] for e, _, _ in matches]

    # CP4-R4: a high-specificity archetype keeps the primary label rather than
    # being absorbed into Hybrid. Co-matches are retained, never discarded.
    preferred = next(((e, r, a) for name in precedence
                      for e, r, a in matches if e["name"] == name), None)

    if preferred is not None:
        entry, reasons, _ = preferred
        why = (f"{entry['name']}: {entry['description']} Rules satisfied — "
               + "; ".join(reasons) + ".")
        others = [n for n in matched_names if n != entry["name"]]
        if others:
            why += (f" Takes the primary label ahead of Hybrid (high-specificity "
                    f"archetype); also matched, retained as secondary: "
                    + ", ".join(f"{n} ({shares[n]:.0%} of role-months)" for n in others)
                    + ".")
        highlights = list(dict.fromkeys(
            entry["highlights"] + [h for e, _, _ in material for h in e["highlights"]]))
        missing_candidates = entry["missing_candidates"]
    elif len(material) >= hcfg["min_matching_archetypes"] and hybrid_entry is not None:
        entry = hybrid_entry
        why = (f"Hybrid: {len(material)} archetypes each carry >= "
               f"{hcfg['min_role_month_share']:.0%} of measured role-months — "
               + "; ".join(f"{e['name']} ({shares[e['name']]:.0%}: "
                           + "; ".join(rs) + ")" for e, rs, _ in material)
               + ". Constituents are named rather than one being discarded.")
        highlights = list(dict.fromkeys(
            [h for e, _, _ in material for h in e["highlights"]] + entry["highlights"]))
        missing_candidates = list(dict.fromkeys(
            [m for e, _, _ in material for m in e["missing_candidates"]]))
    else:
        entry, reasons, _ = matches[0]          # config order = precedence
        why = (f"{entry['name']}: {entry['description']} Rules satisfied — "
               + "; ".join(reasons) + ".")
        if len(matches) > 1:
            others = ", ".join(f"{e['name']} ({shares[e['name']]:.0%} of role-months)"
                               for e, _, _ in matches[1:])
            why += (f" Also matched but below the {hcfg['min_role_month_share']:.0%} "
                    f"Hybrid share gate: {others}.")
        highlights = entry["highlights"]
        missing_candidates = entry["missing_candidates"]

    strong = [h for h in highlights
              if _resolve_highlight(h, sig_map, profile, exceptional_flag)]
    missing = [m for m in missing_candidates
               if not _resolve_highlight(m, sig_map, profile, exceptional_flag)]

    return ArchetypeResult(archetype=entry["name"], strong_signals=strong,
                           missing_for_archetype=missing, explanation=why,
                           matched=matched_names,
                           secondary=[n for n in matched_names if n != entry["name"]],
                           shares=shares)
