// Core data types for the lex-flavored OSS Auditor POC.
//
// These mirror the Pydantic models in `oss_auditor/models.py`, but
// scoped to what the verdict + scoring layer actually consumes —
// not the whole pipeline (no findings, no raw blobs, no LLM
// metadata). Everything here is pure data; no [io] effects.

type DataStatus = Available | Skipped | Unavailable

type Grade = Platinum | Gold | Silver | Bronze | Fail

type Band = Low | Medium | High | NA

type RepoType = Implementation | Proposal


type Technical = Technical({
  score        :: Float,
  data_status  :: DataStatus,
})

type Business = Business({
  score                     :: Float,
  data_status               :: DataStatus,
  problem_clarity           :: Float,
  differentiation           :: Float,
  intellectual_contribution :: Float,
  market_signals            :: Float,
  execution_vs_ambition     :: Float,
})

type Community = Community({
  score        :: Float,
  data_status  :: DataStatus,
})

type Report = Report({
  repo_type :: RepoType,
  technical :: Technical,
  business  :: Business,
  community :: Community,
})


type Verdict = Verdict({
  code           :: Str,
  label          :: Str,
  one_liner      :: Str,
  idea_band      :: Band,
  execution_band :: Band,
  relevance_band :: Band,
})

// Convenience triple used by the verdict matrix.
type Bands = Bands({
  idea      :: Band,
  execution :: Band,
  relevance :: Band,
})

// Output of `compute_overall`.
type Outcome = Outcome({
  score :: Float,
  grade :: Grade,
})
