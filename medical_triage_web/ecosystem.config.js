module.exports = {
  apps: [{
    name: 'medical-triage',
    script: '/opt/medical_triage/web_server.py',
    interpreter: 'python3',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production',
      PORT: 5001
    },
    log_file: '/var/log/medical-triage/combined.log',
    out_file: '/var/log/medical-triage/out.log',
    error_file: '/var/log/medical-triage/error.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};
