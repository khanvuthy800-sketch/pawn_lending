from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    engine_number = fields.Char(string='Engine Number')
    frame_number = fields.Char(string='Frame Number')
    plate_number = fields.Char(string='Plate Number')
    brand = fields.Char(string='Brand')
    model = fields.Char(string='Model')
    color = fields.Char(string='Color')
    year = fields.Integer(string='Year')
    condition = fields.Selection(
        selection=[
            ('new', 'New'),
            ('good', 'Good'),
            ('fair', 'Fair'),
            ('poor', 'Poor'),
        ],
        string='Condition',
    )
    # Phone-specific fields
    imei = fields.Char(string='IMEI')
    storage = fields.Char(string='Storage')
    battery_health = fields.Integer(string='Battery Health (%)')
    accessories = fields.Char(string='Accessories')
    icloud_lock = fields.Boolean(string='iCloud Lock')

    owner_id = fields.Many2one('res.partner', string='Owner')
    pawn_collateral_id = fields.Many2one('pawn.collateral', string='Collateral', ondelete='set null')
    estimated_value = fields.Monetary(string='Estimated Value', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    image = fields.Binary(string='Image', attachment=True)
