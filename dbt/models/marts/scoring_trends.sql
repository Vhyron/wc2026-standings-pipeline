-- Per-tournament scoring profile. Built from match scores, which are
-- complete for all years, not from goal events (sparse 1954-2010).

select
    year,
    count(*)                                        as matches,
    sum(goals1 + goals2)                            as total_goals,
    round(avg(goals1 + goals2), 2)                  as goals_per_match,
    count(*) filter (where winner is null)          as draws,
    round(count(*) filter (where winner is null) * 1.0 / count(*), 3) as draw_rate,
    count(*) filter (where decided_by = 'extra time') as decided_in_extra_time,
    count(*) filter (where decided_by = 'penalties')  as decided_on_penalties
from {{ ref('int_match_outcomes') }}
group by year
order by year
