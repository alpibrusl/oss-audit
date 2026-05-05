# Aggregate score + grade — pure functional port of
# `rubric/reporter/scorer.py::compute_overall`.
#
# Renormalize over `Skipped` pillars only. `Unavailable` pillars
# keep their weight and contribute 0 — missing data is information,
# not an opt-out. Cap the grade at Bronze when fewer than 2
# pillars carry real data.

import "std.float" as float
import "std.int"   as int

import "./models" as m


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
  let t := if is_skipped(r.technical.data_status) { w_technical() } else { 0.0 }
  let b := if is_skipped(r.business.data_status)  { w_business()  } else { 0.0 }
  let c := if is_skipped(r.community.data_status) { w_community() } else { 0.0 }
  t + b + c
}

fn weighted_sum(r :: m.Report) -> Float {
  let t := if is_available(r.technical.data_status) {
             r.technical.score * w_technical()
           } else { 0.0 }
  let b := if is_available(r.business.data_status) {
             r.business.score * w_business()
           } else { 0.0 }
  let c := if is_available(r.community.data_status) {
             r.community.score * w_community()
           } else { 0.0 }
  t + b + c
}

fn n_available(r :: m.Report) -> Int {
  let t := if is_available(r.technical.data_status) { 1 } else { 0 }
  let b := if is_available(r.business.data_status)  { 1 } else { 0 }
  let c := if is_available(r.community.data_status) { 1 } else { 0 }
  t + b + c
}


# floor(x * 10 + 0.5) / 10 — sidesteps a float.round dependency.
fn round1(x :: Float) -> Float {
  int.to_float(float.to_int(x * 10.0 + 0.5)) / 10.0
}

# Fewer than 2 axes of evidence is calibration noise. Cap at Bronze.
fn grade_for(overall :: Float, n :: Int) -> m.Grade {
  if n < 2 {
    if overall >= 40.0 { Bronze } else { Fail }
  } else {
    if overall >= 90.0 {
      if n >= 3 { Platinum } else { Gold }
    } else {
      if overall >= 75.0 { Gold }
      else {
        if overall >= 60.0 { Silver }
        else {
          if overall >= 40.0 { Bronze } else { Fail }
        }
      }
    }
  }
}


fn compute_overall(r :: m.Report) -> m.Outcome {
  let n := n_available(r)
  if n == 0 {
    { score: 0.0, grade: Fail }
  } else {
    let denom   := 1.0 - skipped_weight(r)
    let raw     := weighted_sum(r) / denom
    let rounded := round1(raw)
    { score: rounded, grade: grade_for(rounded, n) }
  }
}
