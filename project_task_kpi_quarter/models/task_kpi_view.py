# -*- coding: utf-8 -*-
from odoo import fields, models, tools

class TaskKPI(models.Model):
    _name = 'project.task.kpi'
    _description = 'Task KPI by Employee/Year/Quarter'
    _auto = False
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', string='Çalışan', index=True)
    project_id = fields.Many2one('project.project', string='Proje', index=True)
    year = fields.Integer(string='Yıl', index=True)
    quarter = fields.Selection(
        [('1', 'Q1'), ('2', 'Q2'), ('3', 'Q3'), ('4', 'Q4')],
        string='Çeyrek', index=True
    )

    backlog_count = fields.Integer(string='Backlog')
    todo_count = fields.Integer(string='To Do')
    inprogress_count = fields.Integer(string='In Progress')
    done_count = fields.Integer(string='Done')
    total_count = fields.Integer(string='Toplam')
    done_pct = fields.Float(string='Done %', digits=(16, 2))

    def init(self):
        tools.drop_view_if_exists(self._cr, 'project_task_kpi')
        self._cr.execute("""
            CREATE VIEW project_task_kpi AS
            SELECT
                ROW_NUMBER() OVER() AS id,
                rel.user_id AS user_id,
                t.project_id AS project_id,

                /* Dönem - önce done_date, yoksa create_date */
                COALESCE(
                    t.x_year,
                    EXTRACT(YEAR FROM COALESCE(t.done_date, t.create_date))::int
                ) AS year,

                /* x_quarter varchar -> hepsini TEXT yap */
                COALESCE(
                    t.x_quarter::text,
                    (EXTRACT(QUARTER FROM COALESCE(t.done_date, t.create_date))::int)::text
                ) AS quarter,

                /* Stage dağılımları */
                SUM(CASE WHEN st.is_closed IS DISTINCT FROM TRUE 
                          AND lower(st.name) LIKE 'backlog%' THEN 1 ELSE 0 END) AS backlog_count,

                SUM(CASE WHEN st.is_closed IS DISTINCT FROM TRUE 
                          AND lower(st.name) LIKE 'to do%' THEN 1 ELSE 0 END) AS todo_count,

                SUM(CASE WHEN st.is_closed IS DISTINCT FROM TRUE 
                          AND lower(st.name) LIKE 'in progress%' THEN 1 ELSE 0 END) AS inprogress_count,

                SUM(CASE WHEN COALESCE(st.is_closed, FALSE) THEN 1 ELSE 0 END) AS done_count,

                COUNT(*) AS total_count,

                CASE WHEN COUNT(*) = 0 THEN 0
                     ELSE (SUM(CASE WHEN COALESCE(st.is_closed, FALSE) THEN 1 ELSE 0 END)::float
                           / COUNT(*)::float) * 100
                END AS done_pct

            FROM project_task t
            LEFT JOIN project_task_type st ON st.id = t.stage_id
            LEFT JOIN project_task_user_rel rel ON rel.task_id = t.id
            GROUP BY
                rel.user_id,
                t.project_id,
                COALESCE(t.x_year, EXTRACT(YEAR FROM COALESCE(t.done_date, t.create_date))::int),
                COALESCE(t.x_quarter::text, (EXTRACT(QUARTER FROM COALESCE(t.done_date, t.create_date))::int)::text)
        """)
