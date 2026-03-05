from odoo import fields, models


class PawnRuleProfile(models.Model):
    _name = 'pawn.rule.profile'
    _description = 'Pawn Rule Profile'
    _order = 'name'

    name = fields.Char(required=True)
    interest_type = fields.Selection(
        selection=[
            ('flat', 'Flat'),
            ('daily', 'Daily'),
            ('monthly', 'Monthly'),
        ],
        required=True,
        default='flat',
    )
    interest_rate = fields.Float(required=True, help='Interest rate in percent.')
    penalty_rate = fields.Float(required=True, help='Penalty rate in percent per overdue day.')
    max_ltv = fields.Float(string='Max LTV (%)', required=True)
    grace_days = fields.Integer(default=0)
    active = fields.Boolean(default=True)

    _check_max_ltv_non_negative = models.Constraint(
        'CHECK(max_ltv >= 0)',
        'Max LTV must be non-negative.',
    )
    _check_interest_rate_non_negative = models.Constraint(
        'CHECK(interest_rate >= 0)',
        'Interest rate must be non-negative.',
    )
    _check_penalty_rate_non_negative = models.Constraint(
        'CHECK(penalty_rate >= 0)',
        'Penalty rate must be non-negative.',
    )
