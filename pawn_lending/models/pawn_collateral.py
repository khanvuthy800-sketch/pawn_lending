from odoo import api, fields, models
from odoo.exceptions import UserError


class PawnCollateral(models.Model):
    _name = 'pawn.collateral'
    _description = 'Pawn Collateral'
    _order = 'id desc'

    contract_id = fields.Many2one('pawn.contract', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    category = fields.Selection(
        selection=[
            ('gold', 'Gold'),
            ('motorbike', 'Motorbike'),
            ('phone', 'Phone'),
            ('other', 'Other'),
        ],
        default='other',
        required=True,
    )
    description = fields.Text()
    estimated_value = fields.Monetary(currency_field='currency_id', required=True)
    serial_number = fields.Char()
    photo = fields.Binary(attachment=True)
    stock_move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    product_id = fields.Many2one(
        'product.product',
        copy=False,
        domain="[('type', '=', 'consu'), ('active', '=', True)]",
    )
    lot_id = fields.Many2one(
        'stock.production.lot',
        string='Serial/Lot',
        copy=False,
        domain="[('product_id', '=', product_id)]",
    )
    engine_number = fields.Char(related='lot_id.engine_number', readonly=False)
    frame_number = fields.Char(related='lot_id.frame_number', readonly=False)
    plate_number = fields.Char(related='lot_id.plate_number', readonly=False)
    brand = fields.Char(related='lot_id.brand', readonly=False)
    model = fields.Char(related='lot_id.model', readonly=False)
    color = fields.Char(related='lot_id.color', readonly=False)
    year = fields.Integer(related='lot_id.year', readonly=False)
    condition = fields.Selection(
        related='lot_id.condition',
        readonly=False,
    )
    currency_id = fields.Many2one(
        'res.currency', related='contract_id.currency_id', store=True, readonly=True
    )

    _check_estimated_value_non_negative = models.Constraint(
        'CHECK(estimated_value >= 0)',
        'Estimated value must be non-negative.',
    )

    def _get_vault_location(self):
        return self.sudo().env.ref('pawn_lending.stock_location_pawn_vault')

    def _get_customer_location(self):
        return self.sudo().env.ref('stock.stock_location_customers')

    def _get_internal_picking_type(self):
        company = self.env.company
        return self.sudo().env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', 'in', [company.id, False])],
            limit=1,
        )

    def _prepare_lot_vals(self):
        self.ensure_one()
        lot_name = self.serial_number or self.name
        if not lot_name:
            raise UserError('Serial number is required to create a collateral lot.')
        return {
            'name': lot_name,
            'product_id': self.product_id.id,
            'company_id': self.contract_id.company_id.id,
            'engine_number': self.engine_number,
            'frame_number': self.frame_number,
            'plate_number': self.plate_number,
            'brand': self.brand,
            'model': self.model,
            'color': self.color,
            'year': self.year,
            'condition': self.condition,
            'owner_id': self.contract_id.customer_id.id,
            'pawn_collateral_id': self.id,
            'estimated_value': self.estimated_value,
            'image': self.photo,
        }

    def _sync_lot(self):
        for collateral in self:
            if not collateral.product_id:
                continue
            if collateral.lot_id and collateral.lot_id.product_id != collateral.product_id:
                collateral.lot_id = False
            vals = collateral._prepare_lot_vals()
            if collateral.lot_id:
                collateral.lot_id.sudo().write(vals)
            else:
                lot = self.env['stock.production.lot'].sudo().create(vals)
                collateral.lot_id = lot.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_lot()
        return records

    def write(self, vals):
        res = super().write(vals)
        sync_fields = {
            'product_id',
            'lot_id',
            'serial_number',
            'name',
            'engine_number',
            'frame_number',
            'plate_number',
            'brand',
            'model',
            'color',
            'year',
            'condition',
            'estimated_value',
            'photo',
        }
        if sync_fields.intersection(vals):
            self._sync_lot()
        return res

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for collateral in self:
            if not collateral.product_id:
                continue
            if collateral.lot_id and collateral.lot_id.product_id != collateral.product_id:
                collateral.lot_id = False
            if not collateral.name:
                collateral.name = collateral.product_id.display_name
            if not collateral.estimated_value:
                collateral.estimated_value = collateral.product_id.lst_price

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        for collateral in self:
            if not collateral.lot_id:
                continue
            collateral.product_id = collateral.lot_id.product_id
            collateral.serial_number = collateral.lot_id.name
            if not collateral.name:
                collateral.name = collateral.lot_id.product_id.display_name
            if not collateral.estimated_value:
                collateral.estimated_value = collateral.lot_id.estimated_value

    def _create_stock_move(self, source_location, dest_location):
        self.ensure_one()
        if not self.product_id:
            raise UserError('Collateral product is missing.')
        self._sync_lot()
        if not self.lot_id:
            raise UserError('Serial/Lot is missing for this collateral.')
        product = self.product_id
        picking_type = self._get_internal_picking_type()
        move = self.sudo().env['stock.move'].create(
            {
                'product_id': product.id,
                'description_picking': self.name,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'picking_type_id': picking_type.id if picking_type else False,
                'origin': self.contract_id.name,
                'company_id': self.contract_id.company_id.id,
                'restrict_lot_id': self.lot_id.id,
                'move_line_ids': [(0, 0, {
                    'product_id': product.id,
                    'lot_id': self.lot_id.id,
                    'qty_done': 1.0,
                    'product_uom_id': product.uom_id.id,
                    'location_id': source_location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': self.contract_id.company_id.id,
                })],
            }
        )
        move._action_done()
        self.stock_move_id = move.id

    def action_move_to_vault(self):
        for collateral in self:
            vault_location = collateral._get_vault_location()
            if (
                collateral.stock_move_id
                and collateral.stock_move_id.state == 'done'
                and collateral.stock_move_id.location_dest_id == vault_location
            ):
                continue
            collateral._create_stock_move(collateral._get_customer_location(), vault_location)

    def action_return_to_customer(self):
        for collateral in self:
            if not collateral.product_id:
                raise UserError('Collateral product is missing. Cannot return to customer.')
            if not collateral.lot_id:
                raise UserError('Collateral lot is missing. Cannot return to customer.')
            collateral._create_stock_move(collateral._get_vault_location(), collateral._get_customer_location())
