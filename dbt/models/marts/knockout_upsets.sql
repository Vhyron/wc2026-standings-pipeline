-- Knockout matches won by the team with the worse group-stage record in
-- the same tournament (fewer points, or equal points and worse goal
-- difference). A proxy for "upset" — the source has no world rankings.
-- Pure-knockout tournaments (1934, 1938) drop out via the joins.

with knockouts as (

    select *
    from {{ ref('int_match_outcomes') }}
    where stage = 'knockout' and winner is not null

)

select
    k.year,
    k.round,
    k.match_date,
    k.winner,
    k.loser,
    case when k.winner = k.team1
         then k.goals1 || '-' || k.goals2
         else k.goals2 || '-' || k.goals1
    end                                           as score,  -- winner's goals first
    k.decided_by,
    w.points                                      as winner_group_points,
    l.points                                      as loser_group_points,
    w.goal_difference                             as winner_group_gd,
    l.goal_difference                             as loser_group_gd,
    l.points - w.points                           as points_gap
from knockouts k
join {{ ref('standings') }} w on w.year = k.year and w.team = k.winner
join {{ ref('standings') }} l on l.year = k.year and l.team = k.loser
where l.points > w.points
   or (l.points = w.points and l.goal_difference > w.goal_difference)
order by points_gap desc, year
