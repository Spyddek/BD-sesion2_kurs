WITH dept_staff AS (
    SELECT d.department_id, d.name, COUNT(e.employee_id) AS staff_cnt
    FROM departments d
    LEFT JOIN employees e ON e.department_id = d.department_id
    GROUP BY d.department_id, d.name
),
dept_leave AS (
    SELECT e.department_id, COUNT(DISTINCT l.employee_id) AS on_leave
    FROM leaves l
    JOIN employees e ON e.employee_id = l.employee_id
    WHERE l.status = 'approved'
      AND CURRENT_DATE BETWEEN l.start_date AND l.end_date
    GROUP BY e.department_id
),
dept_rate AS (
    SELECT e.department_id, ROUND(AVG(p.hourly_rate),2) AS avg_rate
    FROM employees e
    JOIN positions p ON e.position_id = p.position_id
    GROUP BY e.department_id
)
SELECT ds.name AS department,
       ds.staff_cnt,
       COALESCE(dl.on_leave,0) AS on_leave_now,
       dr.avg_rate
FROM dept_staff ds
LEFT JOIN dept_leave dl ON dl.department_id = ds.department_id
LEFT JOIN dept_rate dr ON dr.department_id = ds.department_id
ORDER BY ds.name;