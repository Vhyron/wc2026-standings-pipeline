-- One row per team per played match: each match unpivoted into two
-- team-perspective rows. Standings aggregate this; later analytics
-- (upsets, form, win rates) read it too.

with matches as (

    select * from {{ ref('stg_matches') }}
    where played

),

unpivoted as (

    select year, match_id, match_key, stage, match_group, match_date,
           team1 as team, team2 as opponent,
           score1_ft as goals_for, score2_ft as goals_against
    from matches

    union all

    select year, match_id, match_key, stage, match_group, match_date,
           team2 as team, team1 as opponent,
           score2_ft as goals_for, score1_ft as goals_against
    from matches

)

select
    *,
    case
        when goals_for > goals_against then 'win'
        when goals_for < goals_against then 'loss'
        else 'draw'
    end as result,
    case
        -- FIFA awarded 2 points per win before 1994, 3 since.
        when goals_for > goals_against then (case when year < 1994 then 2 else 3 end)
        when goals_for < goals_against then 0
        else 1
    end as points
from unpivoted
