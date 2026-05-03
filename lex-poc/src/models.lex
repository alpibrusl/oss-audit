# Core data types for the lex-flavored OSS Auditor POC.
#
# Mirror the Pydantic models in `oss_auditor/models.py`, scoped
# to what the verdict + scoring layer consumes. Pure data; no
# [io] effects.

type DataStatus = Available | Skipped | Unavailable
type Grade      = Platinum | Gold | Silver | Bronze | Fail
type Band       = Low | Medium | High | NA
type RepoType   = Implementation | Proposal


type Technical = {
  score       :: Float,
  data_status :: DataStatus,
}

type Business = {
  score                     :: Float,
  data_status               :: DataStatus,
  problem_clarity           :: Float,
  differentiation           :: Float,
  intellectual_contribution :: Float,
  market_signals            :: Float,
  execution_vs_ambition     :: Float,
}

type Community = {
  score       :: Float,
  data_status :: DataStatus,
}

type Report = {
  repo_type :: RepoType,
  technical :: Technical,
  business  :: Business,
  community :: Community,
}


type Verdict = {
  code           :: Str,
  label          :: Str,
  one_liner      :: Str,
  idea_band      :: Band,
  execution_band :: Band,
  relevance_band :: Band,
}

type Bands = {
  idea      :: Band,
  execution :: Band,
  relevance :: Band,
}

type Outcome = {
  score :: Float,
  grade :: Grade,
}
