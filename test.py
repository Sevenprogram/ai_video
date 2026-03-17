{
  "meta": {
    "lastTouchedVersion": "2026.3.13",
    "lastTouchedAt": "2026-03-15T08:10:44.000Z"
  },
  "env": {
    "OPENROUTER_API_KEY": "你的原有的key",
    "MOONSHOT_API_KEY": "sk-GR3Q7Q8WXL47h28hrpzwJeRmsIK2mFamwSTmQUue3zgLJLT9"
  },
  "wizard": {
    "lastRunAt": "2026-03-15T08:05:51.040Z",
    "lastRunVersion": "2026.3.13",
    "lastRunCommand": "configure",
    "lastRunMode": "local"
  },
  "browser": {
    "enabled": true,
    "headless": true,
    "noSandbox": true,
    "defaultProfile": "openclaw",
    "profiles": {
      "openclaw": {
        "cdpPort": 18800,
        "color": "#FF4500"
      }
    }
  },
  "auth": {
    "profiles": {
      "moonshot:default": {
        "provider": "moonshot",
        "mode": "api_key"
      },
      "qwen-portal:default": {
        "provider": "qwen-portal",
        "mode": "oauth"
      },
      "byteplus:default": {
        "provider": "byteplus",
        "mode": "api_key"
      },
      "jeniya:default":{
        "provider":"jeniya",
        "mode":"api_key"
      }
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "jeniya": {
        "baseUrl": "https://jeniya.top/v1",
        "apiKey": "sk-q9oguhgaOxnNukTVpGT7REKFB3JaT2CFkUHQ6fW7kjkVlj9e",
        "api": "openai-completions",
        "models": [
          {
            "id": "claude-3-5-sonnet-20241022",
            "name": "Claude 3.5 Sonnet",
            "reasoning": false,
            "input": [
              "text",
              "image"
            ],
            "contextWindow": 200000,
            "maxTokens": 8192,
            "compat": {
              "supportsDeveloperRole": true
            }
          }
        ]
      },
      "moonshot": {
        "baseUrl": "https://api.moonshot.cn/v1",
        "apiKey": "sk-GR3Q7Q8WXL47h28hrpzwJeRmsIK2mFamwSTmQUue3zgLJLT9",
        "api": "openai-completions",
        "models": [
          {
            "id": "kimi-k2.5",
            "name": "Kimi K2.5",
            "reasoning": false,
            "input": [
              "text",
              "image"
            ],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": 256000,
            "maxTokens": 8192
          }
        ]
      },
      "qwen-portal": {
        "baseUrl": "https://portal.qwen.ai/v1",
        "apiKey": "qwen-oauth",
        "api": "openai-completions",
        "models": [
          {
            "id": "coder-model",
            "name": "Qwen Coder",
            "reasoning": false,
            "input": [
              "text"
            ],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": 128000,
            "maxTokens": 8192
          },
          {
            "id": "vision-model",
            "name": "Qwen Vision",
            "reasoning": false,
            "input": [
              "text",
              "image"
            ],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": 128000,
            "maxTokens": 8192
          }
        ]
      },
      "bailian": {
        "baseUrl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "apiKey": "sk-51aaf7359f4e424395c634aac273323b",
        "api": "openai-completions",
        "models": [
          {
            "id": "qwen3.5-plus",
            "name": "qwen3.5-plus",
            "reasoning": false,
            "contextWindow": 1000000,
            "maxTokens": 65536
          },
          {
            "id": "qwen3-max-2026-01-23",
            "name": "qwen3-max-2026-01-23",
            "reasoning": false,
            "contextWindow": 262144,
            "maxTokens": 65536
          }
        ]
      },
      "ark": {
        "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "apiKey": "db2f65e1-67c6-4acf-b06a-ba4426a5b350",
        "api": "openai-completions",
        "models": [
          {
            "id": "doubao-seed-code",
            "name": "doubao-seed-code",
            "reasoning": false,
            "input": [
              "text"
            ],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": 200000,
            "maxTokens": 8192,
            "headers": {
              "X-Client-Request-Id": "ecs-openclaw/0225/unknown"
            },
            "compat": {
              "supportsDeveloperRole": false
            }
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "jeniya/claude-3-5-sonnet-20241022"
      },
      "models": {
        "jeniya/claude-3-5-sonnet-20241022": {}
      },
      "compaction": {
        "mode": "safeguard"
      },
      "maxConcurrent": 4,
      "subagents": {
        "maxConcurrent": 8
      }
    }
  },
  "messages": {
    "ackReactionScope": "group-mentions"
  },
  "commands": {
    "native": "auto",
    "nativeSkills": "auto",
    "restart": true,
    "ownerDisplay": "raw"
  },
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_a93aa1717ff8dbc6",
      "appSecret": "MrPyye47Z9wSZz0sUGqnrni08ELnLwdm",
      "connectionMode": "websocket",
      "domain": "feishu",
      "groupPolicy": "open",
      "groups": {
        "oc_10e5e1d2510be2545d0b9c703b8b9e9d": {
          "requireMention": false
        }
      }
    }
  },
  "gateway": {
    "mode": "local",
    "auth": {
      "mode": "token",
      "token": "5bb212684b30582f67e139437e555ad58869b6aea2915d60"
    }
  },
  "plugins": {
    "load": {
      "paths": [
        "/usr/lib/node_modules/openclaw/extensions/feishu"
      ]
    },
    "entries": {
      "feishu": {
        "enabled": true
      },
      "qwen-portal-auth": {
        "enabled": true
      }
    }
  }
}