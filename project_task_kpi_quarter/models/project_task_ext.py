# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # Görev, Done (kapalı) aşamasına İLK geçtiği an kaydedilir.
    done_date = fields.Datetime(
        string='Done Tarihi',
        readonly=True, copy=False, index=True,
        help="Görev Done aşamasına ilk geçtiği tarih/saat."
    )

    # Raporlama dönem alanları: Done tarihi varsa ona; yoksa create_date'e göre hesaplanır.
    x_year = fields.Integer(string='Yıl', compute='_compute_periods', store=True, index=True)
    x_quarter = fields.Selection(
        [('1', 'Q1'), ('2', 'Q2'), ('3', 'Q3'), ('4', 'Q4')],
        string='Çeyrek', compute='_compute_periods', store=True, index=True
    )

    # Kapalı stage tespiti: is_closed varsa onu, yoksa fold'u kullan.
    def _is_stage_closed(self, stage):
        if not stage:
            return False
        val = getattr(stage, 'is_closed', None)
        return bool(val if val is not None else getattr(stage, 'fold', False))

    @api.depends('create_date', 'done_date')
    def _compute_periods(self):
        for rec in self:
            dt = rec.done_date or rec.create_date
            if dt:
                rec.x_year = dt.year
                rec.x_quarter = str(((dt.month - 1) // 3) + 1)
            else:
                rec.x_year = False
                rec.x_quarter = False

    @api.model
    def create(self, vals):
        # Kayıt kapalı (Done) bir stage'de oluşturuluyorsa done_date'i hemen ata.
        stage_id = vals.get('stage_id')
        if stage_id:
            stage = self.env['project.task.type'].browse(stage_id)
            if self._is_stage_closed(stage):
                vals.setdefault('done_date', fields.Datetime.now())
        return super().create(vals)

    def write(self, vals):
        # Önce normal yaz, sonra stage değişimi varsa Done/geri alma mantığını uygula.
        res = super().write(vals)

        if 'stage_id' in vals:
            for task in self:
                is_closed_now = self._is_stage_closed(task.stage_id)

                if is_closed_now and not task.done_date:
                    # Done'a İLK geçiş anını kaydet.
                    task.sudo().with_context(tracking_disable=True).write({
                        'done_date': fields.Datetime.now()
                    })
                elif task.done_date and not is_closed_now:
                    # Done'dan GERİ ALINDI: Done sayılmaması için done_date'i temizle.
                    task.sudo().with_context(tracking_disable=True).write({
                        'done_date': False
                    })

        return res
