// Aggregate score + grade — pure functional port of
// `oss_auditor/reporter/scorer.py::compute_overall`.
//
// Renormalize over `Skipped` pillars only. `Unavailable` pillars
// keep their weight and contribute 0 — missing data is information,
// not an opt-out. Cap the grade at Bronze when fewer than 2
// pillars carry real data.

import "std.list" as list

import "./models" as m


// --- destructure helpers (no `.field` access assumed) -----------

fn tech_status(r :: m.Report) -> m.DataStatus {
  match r {
    Report({ technical: Technical({ data_status }) }) => data_status,
  }
}

fn tech_score(r :: m.Report) -> Float {
  match r {
    Report({ technical: Technical({ score }) }) => score,
  }
}

fn biz_status(r :: m.Report) -> m.DataStatus {
  match r {
    Report({ business: Business({ data_status }) }) => data_status,
  }
}

fn biz_score(r :: m.Report) -> Float {
  match r {
    Report({ business: Business({ score }) }) => score,
  }
}

fn com_status(r :: m.Report) -> m.DataStatus {
  match r {
    Report({ community: Community({ data_status }) }) => data_status,
  }
}

fn com_score(r :: m.Report) -> Float {
  match r {
    Report({ community: Community({ score }) }) => score,
  }
}


// --- weights ----------------------------------------------------

fn w_technical() -> Float { 0.40 }
fn w_business()  -> Float { 0.35 }
fn w_community() -> Float { 0.25 }


fn is_available(s :: m.DataStatus) -> Bool {
  match s { Available => true, _ => false }
}

fn is_skipped(s :: m.DataStatus) -> Bool {
  match s { Skipped => true, _ => false }
}


fn skipped_weight(r :: m.Report) -> Float {
  let t := if is_skipped(tech_status(r)) { w_technical() } else { 0.0 }
  let b := if is_skipped(biz_status(r))  { w_business()  } else { 0.0 }
  let c := if is_skipped(com_status(r))  { w_community() } else { 0.0 }
  t + b + c
}

fn weighted_sum(r :: m.Report) -> Float {
  let t := if is_available(tech_status(r)) { tech_score(r) * w_technical() } else { 0.0 }
  let b := if is_available(biz_status(r))  { biz_score(r)  * w_business()  } else { 0.0 }
  let c := if is_available(com_status(r))  { com_score(r)  * w_community() } else { 0.0 }
  t + b + c
}

fn n_available(r :: m.Report) -> Int {
  let t := if is_available(tech_status(r)) { 1 } else { 0 }
  let b := if is_available(biz_status(r))  { 1 } else { 0 }
  let c := if is_available(com_status(r))  { 1 } else { 0 }
  t + b + c
}


// Grade selection with axis-count cap. Mirrors scorer.py exactly.
fn grade_for(overall :: Float, n :: Int) -> m.Grade {
  if n < 2 {
    // Fewer than 2 axes of evidence is calibration noise. Cap at Bronze.
    if overall >= 40.0 { Bronze } else { Fail }
  } else if overall >= 90.0 {
    if n >= 3 { Platinum } else { Gold }
  } else if overall >= 75.0 {
    Gold
  } else if overall >= 60.0 {
    Silver
  } else if overall >= 40.0 {
    Bronze
  } else {
    Fail
  }
}


fn compute_overall(r :: m.Report) -> m.Outcome {
  let n := n_available(r)
  if n == 0 {
    Outcome({ score: 0.0, grade: Fail })
  } else {
    let denom   := 1.0 - skipped_weight(r)
    let raw     := weighted_sum(r) / denom
    // Round to 1 decimal: floor(x * 10 + 0.5) / 10. Avoid std.float
    // dependency for the POC.
    let rounded := int_to_float(float_to_int(raw * 10.0 + 0.5)) / 10.0
    Outcome({ score: rounded, grade: grade_for(rounded, n) })
  }
}
