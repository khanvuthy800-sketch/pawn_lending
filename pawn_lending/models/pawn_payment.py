from odoo import api, fields, models
from odoo.exceptions import UserError


class PawnPayment(models.Model):
    _name = 'pawn.payment'
    _description = 'Pawn Payment'
    _inherit = ['mail.thread']
    _order = 'payment_date desc, id desc'

    contract_id = fields.Many2one('pawn.contract', required=True, ondelete='cascade', index=True)
    payment_type = fields.Selection(
        selection=[
            ('interest', 'Interest'),
            ('principal', 'Principal'),
            ('penalty', 'Penalty'),
        ],
        required=True,
        default='interest',
        tracking=True,
    )
    amount = fields.Monetary(required=True, currency_field='currency_id')
    payment_date = fields.Date(default=fields.Date.context_today, required=True)
    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', contract_id.company_id)]",
    )
    account_move_id = fields.Many2one('account.move', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled')],
        default='draft',
        tracking=True,
        required=True,
    )
    currency_id = fields.Many2one('res.currency', related='contract_id.currency_id', store=True, readonly=True)

    _check_amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Payment amount must be positive.',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'journal_id' in fields_list:
            journal = self.env['pawn.contract']._get_default_journal()
            values['journal_id'] = journal.id if journal else False
        return values

    def action_post(self):
        for payment in self.filtered(lambda p: p.state == 'draft'):
            if payment.contract_id.state not in ('active', 'overdue', 'renewed'):
                raise UserError('Payments can only be posted for active, overdue, or renewed contracts.')
            move, invoice = payment._create_payment_move()
            payment.account_move_id = move.id
            if invoice:
                payment.invoice_id = invoice.id
            payment.state = 'posted'

    def action_cancel(self):
        for payment in self.filtered(lambda p: p.state != 'cancel'):
            payment.state = 'cancel'

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref('pawn_lending.action_report_payment_receipt').report_action(self)

    def _create_payment_move(self):
        self.ensure_one()
        if not self.journal_id.default_account_id:
            raise UserError('Payment journal must have a default account.')

        accounts = self.contract_id._get_config_accounts()
        invoice = False

        if self.payment_type == 'interest':
            credit_account = accounts['interest_income']
        elif self.payment_type == 'penalty':
            credit_account = accounts['penalty_income']
        else:
            credit_account = accounts['receivable']

        if not credit_account:
            raise UserError('Required accounts are missing in Pawn settings.')

        if self.payment_type == 'interest':
            sale_journal = self.env['account.journal'].search([
                ('type', '=', 'sale'), 
                ('company_id', '=', self.contract_id.company_id.id)
            ], limit=1)
            if not sale_journal:
                raise UserError('No Sales Journal found to create an invoice for interest payment.')

            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.contract_id.customer_id.id,
                'journal_id': sale_journal.id,
                'invoice_date': self.payment_date,
                'ref': f'{self.contract_id.name} - Interest Payment',
                'invoice_line_ids': [
                    (0, 0, {
                        'name': f'Interest Payment for {self.contract_id.name}',
                        'quantity': 1,
                        'price_unit': self.amount,
                        'account_id': credit_account.id,
                    })
                ]
            })
            invoice.action_post()
            
            # The payment move should credit the receivable account to reconcile with the invoice
            receivable_lines = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
            if receivable_lines:
                credit_account = receivable_lines[0].account_id
            else:
                credit_account = accounts['receivable']

        move = self.env['account.move'].create(
            {
                'move_type': 'entry',
                'date': self.payment_date,
                'journal_id': self.journal_id.id,
                'ref': f'{self.contract_id.name} - Payment',
                'line_ids': [
                    (0, 0, {
                        'name': self.contract_id.name,
                        'partner_id': self.contract_id.customer_id.id,
                        'account_id': self.journal_id.default_account_id.id,
                        'debit': self.amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': self.contract_id.name,
                        'partner_id': self.contract_id.customer_id.id,
                        'account_id': credit_account.id,
                        'debit': 0.0,
                        'credit': self.amount,
                    }),
                ],
            }
        )
        move.action_post()

        if invoice:
            # Reconcile the payment move with the invoice
            lines_to_reconcile = (invoice.line_ids + move.line_ids).filtered(
                lambda l: l.account_id == credit_account and not l.reconciled
            )
            if len(lines_to_reconcile) > 1:
                lines_to_reconcile.reconcile()

        return move, invoice
