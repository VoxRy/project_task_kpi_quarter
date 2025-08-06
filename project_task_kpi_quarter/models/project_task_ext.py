# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ProjectTask(models.Model):
    _inherit = 'project.task'

    # Görev Done'a ilk geçtiği an kaydedilir
    done_date = fields.Datetime(
        string='Done Tarihi',
        readonly=True, copy=False, index=True,
        help="Görev Done aşamasına ilk geçtiği tarih/saat."
    )
    # Raporlamada kullanılacak dönem alanları
    x_year = fields.Integer(string='Yıl', compute='_compute_periods', store=True, index=True)
    x_quarter = fields.Selection(
        [('1','Q1'),('2','Q2'),('3','Q3'),('4','Q4')],
        string='Çeyrek', compute='_compute_periods', store=True, index=True
    )

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
        # Kayıt Done bir stage'de oluşturuluyorsa hemen done_date ata
        stage_id = vals.get('stage_id')
        if stage_id:
            stage = self.env['project.task.type'].browse(stage_id)
            if stage and getattr(stage, 'is_closed', False):
                vals.setdefault('done_date', fields.Datetime.now())
        return super().create(vals)

    def write(self, vals):
        res = super().write(vals)
        # Stage değiştiyse Done'a geçişi yakala
        if 'stage_id' in vals:
            for task in self:
                st = task.stage_id
                if st and getattr(st, 'is_closed', False) and not task.done_date:
                    # Done'a ilk geçiş anını kaydet
                    task.sudo().with_context(tracking_disable=True).write({
                        'done_date': fields.Datetime.now()
                    })
                # Done'dan geri alındığında done_date'i koruyoruz.
                # Silmek istersen aşağıdaki satırı aç:
                # else:
                #     if task.done_date and not getattr(st, 'is_closed', False):
                #         task.sudo().with_context(tracking_disable=True).write({'done_date': False})
        return res
