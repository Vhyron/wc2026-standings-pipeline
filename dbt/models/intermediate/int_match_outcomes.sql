-- One row per played match with the decided outcome. Knockout matches can
-- be decided after full time, so the winner logic is: penalties if taken,
-- else the extra-time score, else full time. goals1/goals2 are the actual
-- match goals (extra-time score is cumulative; shootout goals don't count).

with matches as (

    select * from {{ ref('stg_matches') }}
    where played

),

scored as (

    select
        *,
        coalesce(score1_et, score1_ft) as goals1,
        coalesce(score2_et, score2_ft) as goals2
    from matches

)

select
    year,
    match_id,
    match_key,
    stage,
    match_group,
    round,
    match_date,
    team1,
    team2,
    goals1,
    goals2,
    case
        when score1_p is not null and score1_p > score2_p then team1
        when score2_p is not null and score2_p > score1_p then team2
        when goals1 > goals2 then team1
        when goals2 > goals1 then team2
    end as winner,
    case
        when score1_p is not null and score1_p > score2_p then team2
        when score2_p is not null and score2_p > score1_p then team1
        when goals1 > goals2 then team2
        when goals2 > goals1 then team1
    end as loser,
    case
        when score1_p is not null then 'penalties'
        when score1_et is not null then 'extra time'
        else 'full time'
    end as decided_by
from scored
