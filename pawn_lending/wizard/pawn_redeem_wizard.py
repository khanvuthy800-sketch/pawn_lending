from odoo import api, fields, models
from odoo.exceptions import UserError

class PawnRedeemWizard(models.TransientModel):
    _name = 'pawn.redeem.wizard'
    _description = 'Pawn Redeem Wizard'

    contract_id = fields.Many2one('pawn.contract', 'Contract', required=True, readonly=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    company_id = fields.Many2one(related='contract_id.company_id')

    principal_amount = fields.Monetary('Principal Amount', currency_field='currency_id', readonly=True)
    interest_amount = fields.Monetary('Interest Amount', currency_field='currency_id', readonly=True)
    penalty_amount = fields.Monetary('Penalty Amount', currency_field='currency_id', readonly=True)
    total_amount = fields.Monetary('Total Amount', currency_field='currency_id', readonly=True)

    payment_date = fields.Date('Payment Date', default=fields.Date.context_today, required=True)
    journal_id = fields.Many2one(
        'account.journal',
        'Payment Journal',
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = self.env.context.get('active_id')
        if contract_id:
            contract = self.env['pawn.contract'].browse(contract_id)
            if contract.state not in ('active', 'overdue', 'renewed'):
                raise UserError('Contracts can only be redeemed if they are active, overdue, or renewed.')
            
            res['contract_id'] = contract.id
            res['principal_amount'] = contract.outstanding_principal
            res['interest_amount'] = contract.total_interest_due
            res['penalty_amount'] = contract.penalty_amount
            res['total_amount'] = contract.outstanding_principal + contract.total_interest_due + contract.penalty_amount
            
            journal = contract._get_default_journal()
            if journal:
                res['journal_id'] = journal.id

        return res

    def action_confirm_redeem(self):
        self.ensure_one()
        
        amounts_to_pay = [
            ('principal', self.principal_amount),
            ('interest', self.interest_amount),
            ('penalty', self.penalty_amount),
        ]
        
        PaymentModel = self.env['pawn.payment']
        
        for payment_type, amount in amounts_to_pay:
            if amount > 0:
                payment = PaymentModel.create({
                    'contract_id': self.contract_id.id,
                    'payment_type': payment_type,
                    'amount': amount,
                    'payment_date': self.payment_date,
                    'journal_id': self.journal_id.id,
                })
                payment.action_post()
        
        self.contract_id.action_redeem()
        return {'type': 'ir.actions.act_window_close'}
