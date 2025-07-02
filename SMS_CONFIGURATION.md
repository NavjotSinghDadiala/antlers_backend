# Gmail OTP Configuration Guide

This application uses Gmail SMTP to send OTP verification codes to users' email addresses.

## Gmail Setup

1. Create a Gmail account (or use an existing one)
2. Enable 2-Step Verification in your Google Account settings
3. Create an App Password (16-digit) for "Mail" and "Other" (see [Google's guide](https://support.google.com/accounts/answer/185833?hl=en))
4. Add the following to your environment variables:
   ```
   GMAIL_USER=your_gmail_address@gmail.com
   GMAIL_PASS=your_16_digit_app_password
   ```

## Environment Variables

Create a `.env` file in your project root with the following variables:

```env
# Gmail OTP Service Configuration
GMAIL_USER=your_gmail_address@gmail.com
GMAIL_PASS=your_16_digit_app_password

# Flask Configuration
SECRET_KEY=your_secret_key_here
```

## Features

- **Real Email Delivery**: OTP is sent to the user's email address
- **Error Handling**: Comprehensive error handling with detailed messages
- **Rate Limiting**: Built-in cooldown for resend functionality
- **Security**: OTP expires after 5 minutes
- **User Experience**: Auto-focus, auto-submit, and input validation

## How It Works

1. User registers with their email address
2. System generates a 6-digit OTP
3. Gmail SMTP sends the OTP to the user's email
4. User enters the OTP received in their inbox
5. System verifies the OTP and activates the account

## Troubleshooting

1. **Email not sending**: Check your Gmail credentials and app password
2. **Gmail security**: Make sure you use an App Password, not your main Gmail password
3. **Rate limiting**: Wait 60 seconds between resend attempts
4. **Network issues**: The system will show appropriate error messages
5. **API errors**: Check your Gmail account for security alerts or blocks 