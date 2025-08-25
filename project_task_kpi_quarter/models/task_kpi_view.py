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
            WITH base AS (
                SELECT
                    rel.user_id,
                    t.project_id,

                    /* Stage adından yıl ayıkla: ".... 2024 Arşiv" vs. */
                    NULLIF(
                        NULLIF(
                            SUBSTRING(LOWER(st.name) FROM '([12][0-9]{3})\\s*ar(s|ş)iv'),  -- "2024 arşiv/arsiv"
                            ''
                        ),
                        NULL
                    )                                                             AS archive_token,
                    SUBSTRING(st.name FROM '([12][0-9]{3})')::int                  AS archive_year,

                    /* Raporda kullanılacak YIL:
                       1) Stage adındaki yıl (Arşiv) varsa onu kullan
                       2) Yoksa x_year
                       3) O da yoksa done_date/create_date yıl
                    */
                    COALESCE(
                        SUBSTRING(st.name FROM '([12][0-9]{3})')::int,
                        t.x_year,
                        EXTRACT(YEAR FROM COALESCE(t.done_date, t.create_date))::int
                    ) AS year,

                    /* ÇEYREK:
                       Arşiv stage'lerinde çoğu zaman çeyrek belirsiz → NULL (Pivot'ta Undefined)
                       Diğerlerinde x_quarter veya tarihten hesap
                    */
                    CASE
                        WHEN LOWER(st.name) ~ '([12][0-9]{3})\\s*ar(s|ş)iv'
                            THEN NULL
                        ELSE COALESCE(
                            t.x_quarter::text,
                            (EXTRACT(QUARTER FROM COALESCE(t.done_date, t.create_date))::int)::text
                        )
                    END AS quarter,

                    st.name AS stage_name,

                    /* DONE sahası:
                       - Stage adı ".... Arşiv" ise DONE say (yılını yukarıda Arşiv yılına koyduk)
                       - Aksi halde sadece Closing Stage (is_closed=True) DONE
                    */
                    CASE
                        WHEN LOWER(st.name) ~ '([12][0-9]{3})\\s*ar(s|ş)iv' THEN TRUE
                        ELSE COALESCE(st.is_closed, FALSE)
                    END AS is_done_stage

                FROM project_task t
                LEFT JOIN project_task_type st ON st.id = t.stage_id
                LEFT JOIN project_task_user_rel rel ON rel.task_id = t.id
            )
            SELECT
                ROW_NUMBER() OVER() AS id,
                user_id,
                project_id,
                year,
                quarter,

                /* Backlog: kapalı olmayan ve adı Backlog ile başlayan */
                SUM(CASE
                        WHEN is_done_stage IS DISTINCT FROM TRUE
                         AND stage_name ILIKE 'Backlog%%'
                    THEN 1 ELSE 0 END
                ) AS backlog_count,

                /* To Do: kapalı olmayan ve adı To Do ile başlayan */
                SUM(CASE
                        WHEN is_done_stage IS DISTINCT FROM TRUE
                         AND stage_name ILIKE 'To Do%%'
                    THEN 1 ELSE 0 END
                ) AS todo_count,

                /* In Progress: kapalı olmayan + Backlog/To Do olmayan (Arşivler DONE kabul edildiği için buraya düşmez) */
                SUM(CASE
                        WHEN is_done_stage IS DISTINCT FROM TRUE
                         AND (stage_name IS NULL
                              OR (stage_name NOT ILIKE 'Backlog%%'
                                  AND stage_name NOT ILIKE 'To Do%%'))
                    THEN 1 ELSE 0 END
                ) AS inprogress_count,

                /* Done: is_done_stage (Arşiv dahil) */
                SUM(CASE WHEN is_done_stage THEN 1 ELSE 0 END) AS done_count,

                COUNT(*) AS total_count,

                CASE WHEN COUNT(*) = 0 THEN 0
                     ELSE (SUM(CASE WHEN is_done_stage THEN 1 ELSE 0 END)::float
                           / COUNT(*)::float) * 100
                END AS done_pct

            FROM base
            GROUP BY user_id, project_id, year, quarter
        """)

    # KPI satırındaki kriterlere göre project.task kayıtlarını aç (drill-down)
    def action_open_tasks(self):
        self.ensure_one()
        domain = []

        if self.user_id:
            # project_task_user_rel -> tasks: user_ids (M2M)
            domain.append(('user_ids', 'in', self.user_id.id))
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        # YIL filtresi: x_year == year  VEYA  stage adı "<year> Arşiv"
        if self.year:
            year_str = str(self.year)
            domain += ['|',
                       ('x_year', '=', self.year),
                       '|',
                       ('stage_id.name', 'ilike', f'%{year_str} arşiv%'),
                       ('stage_id.name', 'ilike', f'%{year_str} arsiv%')]

        # ÇEYREK filtresi: Arşiv satırları için quarter NULL olur; pivotta "Undefined" kolonuna düşer.
        # Kullanıcı Q1..Q4 seçmişse normal x_quarter filtresi çalışır.
        if self.quarter:
            domain.append(('x_quarter', '=', self.quarter))

        metric = (self.env.context or {}).get('metric')

        # Domain, SQL mantığıyla uyumlu:
        # Done = Closing Stage (is_closed=True)  VEYA  "YYYY Arşiv" isimli stage
        if metric == 'done':
            if self.year:
                year_str = str(self.year)
                domain += ['|',
                           ('stage_id.is_closed', '=', True),
                           '|',
                           ('stage_id.name', 'ilike', f'%{year_str} arşiv%'),
                           ('stage_id.name', 'ilike', f'%{year_str} arsiv%')]
            else:
                domain += ['|',
                           ('stage_id.is_closed', '=', True),
                           '|',
                           ('stage_id.name', 'ilike', '% arşiv%'),
                           ('stage_id.name', 'ilike', '% arsiv%')]

        elif metric == 'backlog':
            domain += [
                ('stage_id.is_closed', '!=', True),
                ('stage_id.name', 'ilike', 'backlog%'),
            ]

        elif metric == 'todo':
            domain += [
                ('stage_id.is_closed', '!=', True),
                ('stage_id.name', 'ilike', 'to do%'),
            ]

        elif metric == 'in_progress':
            # Kapalı değil + Backlog/To Do değil + "YYYY Arşiv" de değil
            if self.year:
                year_str = str(self.year)
                domain += [
                    ('stage_id.is_closed', '!=', True),
                    ('stage_id.name', 'not ilike', 'backlog%'),
                    ('stage_id.name', 'not ilike', 'to do%'),
                    ('stage_id.name', 'not ilike', f'%{year_str} arşiv%'),
                    ('stage_id.name', 'not ilike', f'%{year_str} arsiv%'),
                ]
            else:
                domain += [
                    ('stage_id.is_closed', '!=', True),
                    ('stage_id.name', 'not ilike', 'backlog%'),
                    ('stage_id.name', 'not ilike', 'to do%'),
                    ('stage_id.name', 'not ilike', '% arşiv%'),
                    ('stage_id.name', 'not ilike', '% arsiv%'),
                ]
        # metric 'total' veya None ise ekstra stage filtresi yok

        return {
            'type': 'ir.actions.act_window',
            'name': 'Görevler',
            'res_model': 'project.task',
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
            # KPI'ya arşivli (active=False) görevleri dahil etmiyorsanız, burada da default kalsın.
            # Aksi halde hepsini görmek için:
            # 'context': {'active_test': False},
        }
