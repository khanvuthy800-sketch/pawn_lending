from odoo import api, fields, models
from odoo.exceptions import UserError

class PawnSellWizard(models.TransientModel):
    _name = 'pawn.sell.wizard'
    _description = 'Pawn Sell Forfeited Collateral Wizard'

    contract_id = fields.Many2one('pawn.contract', 'Contract', required=True, readonly=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    company_id = fields.Many2one(related='contract_id.company_id')

    buyer_id = fields.Many2one('res.partner', 'Buyer', required=True, domain="[('is_company', '=', False)]")
    sale_price = fields.Monetary('Sale Price', currency_field='currency_id', required=True)
    sale_date = fields.Date('Sale Date', default=fields.Date.context_today, required=True)
    
    principal_amount = fields.Monetary('Principal (Cost)', currency_field='currency_id', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = self.env.context.get('active_id')
        if contract_id:
            contract = self.env['pawn.contract'].browse(contract_id)
            if contract.state != 'forfeited':
                raise UserError('Only forfeited contracts can be sold.')
            
            res['contract_id'] = contract.id
            res['principal_amount'] = contract.outstanding_principal
            res['sale_price'] = contract.outstanding_principal  # Default
        return res

    def action_confirm_sell(self):
        self.ensure_one()
        contract = self.contract_id
        
        accounts = contract._get_config_accounts()
        inventory_account = accounts.get('inventory')
        profit_account = accounts.get('profit')
        
        if not inventory_account:
            raise UserError('Please configure an Inventory Account in Pawn Settings.')
        if not profit_account:
            raise UserError('Please configure a Pawn Profit Account in Pawn Settings.')

        principal = contract.outstanding_principal
        profit = self.sale_price - principal

        # Create Customer Invoice (Accounts Receivable implicitly handled by out_invoice)
        sale_journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', contract.company_id.id)
        ], limit=1)
        
        if not sale_journal:
            raise UserError('No Sales Journal found for this company.')

        invoice_lines = []
        
        # Line 1: Clear Inventory (Credit)
        invoice_lines.append((0, 0, {
            'name': f'Sale of Collateral {contract.name} (Cost Recovery)',
            'account_id': inventory_account.id,
            'price_unit': principal, # This creates a credit
            'quantity': 1,
        }))
        
        # Line 2: Record Profit or Loss (Credit, or Debit if negative)
        if profit != 0:
            invoice_lines.append((0, 0, {
                'name': f'Sale of Collateral {contract.name} (Profit/Loss)',
                'account_id': profit_account.id,
                'price_unit': profit,
                'quantity': 1,
            }))

        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.buyer_id.id,
            'journal_id': sale_journal.id,
            'invoice_date': self.sale_date,
            'ref': f'Sale of {contract.name}',
            'invoice_line_ids': invoice_lines,
        }

        invoice = self.env['account.move'].with_company(contract.company_id).create(move_vals)
        invoice.action_post()

        contract.sold_invoice_id = invoice.id
        contract.state = 'closed'

        return {'type': 'ir.actions.act_window_close'}
