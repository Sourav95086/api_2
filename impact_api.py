import os
import math
from fastapi import FastAPI, HTTPException
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Predictive Social & Economic Impact API",
    version="1.0.0"
)

# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)

    except (ValueError, TypeError):
        return default


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def round_money(value):
    return round(value, 2)


# ============================================================
# GET ISSUE
# ============================================================

def get_issue(issue_id: int):

    response = (
        supabase
        .table("issues")
        .select("*")
        .eq("issue_id", issue_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail=f"Issue {issue_id} not found"
        )

    return response.data[0]


# ============================================================
# GET REPORTS
# ============================================================

def get_issue_reports(issue_id: int):

    response = (
        supabase
        .table("issue_reports")
        .select("*")
        .eq("issue_id", issue_id)
        .execute()
    )

    return response.data or []


# ============================================================
# GET PROPOSED SOLUTION
# ============================================================

def get_proposed_solution(issue_id: int):

    response = (
        supabase
        .table("proposed_solutions")
        .select("*")
        .eq("source_issue_id", issue_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail=f"No proposed solution found for issue {issue_id}"
        )

    return response.data[0]


# ============================================================
# SOCIAL IMPACT
# ============================================================

def calculate_social_impact(solution, report_count):

    demographic_score = safe_float(
        solution.get("demographic_priority_score")
    )

    infrastructure_score = safe_float(
        solution.get("infrastructure_gap_score")
    )

    accessibility_score = safe_float(
        solution.get("accessibility_score")
    )

    severity_score = safe_float(
        solution.get("issue_severity_score")
    )

    urgency_score = safe_float(
        solution.get("urgency_score")
    )

    citizen_demand_score = safe_float(
        solution.get("citizen_demand_score")
    )

    # --------------------------------------------------------
    # Weighted social impact score
    # --------------------------------------------------------

    score = (
        demographic_score * 0.25 +
        infrastructure_score * 0.20 +
        accessibility_score * 0.15 +
        severity_score * 0.15 +
        urgency_score * 0.15 +
        citizen_demand_score * 0.10
    )

    score = clamp(score)

    # --------------------------------------------------------
    # Estimate relative affected population
    #
    # For MVP we use report count as the available proxy.
    # Later this will be replaced/enhanced using demographic API.
    # --------------------------------------------------------

    affected_population_estimate = max(
        report_count * 25,
        report_count
    )

    # Estimated beneficiaries based on social impact score
    beneficiary_ratio = 0.50 + (score / 200)

    beneficiaries = int(
        affected_population_estimate * beneficiary_ratio
    )

    beneficiaries = min(
        beneficiaries,
        affected_population_estimate
    )

    return {
        "score": round(score, 2),
        "affected_population": affected_population_estimate,
        "estimated_beneficiaries": beneficiaries
    }


# ============================================================
# ECONOMIC IMPACT
# ============================================================

def calculate_economic_impact(solution, social_score):

    cost_min = safe_float(
        solution.get("estimated_cost_min")
    )

    cost_max = safe_float(
        solution.get("estimated_cost_max")
    )

    # Safety fallback
    if cost_min <= 0:
        cost_min = 100000

    if cost_max <= 0:
        cost_max = cost_min * 1.25

    if cost_max < cost_min:
        cost_min, cost_max = cost_max, cost_min

    average_cost = (cost_min + cost_max) / 2

    # --------------------------------------------------------
    # MVP benefit estimation
    #
    # Social impact determines expected economic benefit
    # multiplier.
    #
    # Higher impact -> higher potential benefit.
    # --------------------------------------------------------

    benefit_multiplier = 1.0 + (social_score / 100)

    expected_benefit = average_cost * benefit_multiplier

    benefit_min = expected_benefit * 0.75
    benefit_max = expected_benefit * 1.25

    net_min = benefit_min - cost_max
    net_max = benefit_max - cost_min

    ratio_min = benefit_min / cost_max
    ratio_max = benefit_max / cost_min

    return {
        "estimated_cost": {
            "min": round_money(cost_min),
            "max": round_money(cost_max)
        },

        "estimated_benefit": {
            "min": round_money(benefit_min),
            "max": round_money(benefit_max)
        },

        "net_benefit": {
            "min": round_money(net_min),
            "max": round_money(net_max)
        },

        "benefit_cost_ratio": {
            "min": round(ratio_min, 2),
            "max": round(ratio_max, 2)
        }
    }


# ============================================================
# SCENARIOS
# ============================================================

def calculate_scenarios(social_score, economic):

    cost_min = economic["estimated_cost"]["min"]
    cost_max = economic["estimated_cost"]["max"]

    benefit_min = economic["estimated_benefit"]["min"]
    benefit_max = economic["estimated_benefit"]["max"]

    # Worst case
    worst_benefit = benefit_min * 0.85
    worst_cost = cost_max

    # Expected case
    expected_benefit = (
        benefit_min + benefit_max
    ) / 2

    expected_cost = (
        cost_min + cost_max
    ) / 2

    # Best case
    best_benefit = benefit_max * 1.10
    best_cost = cost_min

    return {

        "worst_case": {
            "social_impact_score": round(
                social_score * 0.75,
                2
            ),
            "cost": round_money(worst_cost),
            "benefit": round_money(worst_benefit),
            "net_benefit": round_money(
                worst_benefit - worst_cost
            )
        },

        "expected_case": {
            "social_impact_score": round(
                social_score,
                2
            ),
            "cost": round_money(expected_cost),
            "benefit": round_money(expected_benefit),
            "net_benefit": round_money(
                expected_benefit - expected_cost
            )
        },

        "best_case": {
            "social_impact_score": round(
                min(social_score * 1.15, 100),
                2
            ),
            "cost": round_money(best_cost),
            "benefit": round_money(best_benefit),
            "net_benefit": round_money(
                best_benefit - best_cost
            )
        }
    }


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(solution, report_count):

    data_points = 0

    score_fields = [
        "demographic_priority_score",
        "infrastructure_gap_score",
        "accessibility_score",
        "issue_severity_score",
        "urgency_score",
        "citizen_demand_score"
    ]

    for field in score_fields:

        value = solution.get(field)

        if value is not None:
            data_points += 1

    # More reports = better evidence
    report_factor = min(report_count / 20, 1)

    # Data completeness
    data_factor = data_points / len(score_fields)

    social_confidence = (
        0.50 +
        data_factor * 0.30 +
        report_factor * 0.20
    )

    economic_confidence = (
        0.45 +
        data_factor * 0.25 +
        report_factor * 0.15
    )

    social_confidence = min(
        social_confidence,
        0.95
    )

    economic_confidence = min(
        economic_confidence,
        0.90
    )

    return {
        "social": round(
            social_confidence * 100,
            2
        ),

        "economic": round(
            economic_confidence * 100,
            2
        )
    }


# ============================================================
# UNCERTAINTIES
# ============================================================

def get_uncertainties(solution):

    uncertainties = [
        "Actual implementation cost may vary",
        "Implementation delays may affect outcomes",
        "Actual population response may differ from estimates"
    ]

    if not solution.get("estimated_cost_min"):
        uncertainties.append(
            "Project cost estimate has limited supporting data"
        )

    if not solution.get("demographic_priority_score"):
        uncertainties.append(
            "Demographic data availability is limited"
        )

    if not solution.get("infrastructure_gap_score"):
        uncertainties.append(
            "Infrastructure data availability is limited"
        )

    return uncertainties


# ============================================================
# MAIN ENDPOINT
# ============================================================

@app.post("/predict-impact/{issue_id}")
def predict_impact(issue_id: int):

    # --------------------------------------------------------
    # 1. Get issue
    # --------------------------------------------------------

    issue = get_issue(issue_id)

    # --------------------------------------------------------
    # 2. Get reports
    # --------------------------------------------------------

    reports = get_issue_reports(issue_id)

    report_count = len(reports)

    # --------------------------------------------------------
    # 3. Get proposed solution
    # --------------------------------------------------------

    solution = get_proposed_solution(issue_id)

    # --------------------------------------------------------
    # 4. Social impact
    # --------------------------------------------------------

    social = calculate_social_impact(
        solution,
        report_count
    )

    social_score = social["score"]

    # --------------------------------------------------------
    # 5. Economic impact
    # --------------------------------------------------------

    economic = calculate_economic_impact(
        solution,
        social_score
    )

    # --------------------------------------------------------
    # 6. Scenarios
    # --------------------------------------------------------

    scenarios = calculate_scenarios(
        social_score,
        economic
    )

    # --------------------------------------------------------
    # 7. Confidence
    # --------------------------------------------------------

    confidence = calculate_confidence(
        solution,
        report_count
    )

    # --------------------------------------------------------
    # 8. Uncertainty
    # --------------------------------------------------------

    uncertainties = get_uncertainties(
        solution
    )

    # --------------------------------------------------------
    # 9. Final response
    # --------------------------------------------------------

    return {

        "issue_id": issue_id,

        "issue_category": issue.get(
            "issue_category"
        ),

        "proposed_intervention": solution.get(
            "solution_name"
        ),

        "solution_description": solution.get(
            "solution_description"
        ),

        "location": {
            "city": solution.get("city"),
            "state": solution.get("state"),
            "ward_number": solution.get("ward_number")
        },

        "social_impact": social,

        "economic_impact": economic,

        "scenarios": scenarios,

        "confidence": confidence,

        "uncertainties": uncertainties
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def root():

    return {
        "message": "Predictive Impact API is running",
        "endpoint": "POST /predict-impact/{issue_id}"
    }

@app.get("/solution-source-issue/{solution_id}")
def get_source_issue_id(solution_id: str):
    try:
        response = (
            supabase
            .table("proposed_solutions")
            .select("id, source_issue_id")
            .eq("id", solution_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Solution not found"
            )

        solution = response.data[0]

        return {
            "solution_id": solution["id"],
            "source_issue_id": solution["source_issue_id"]
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )