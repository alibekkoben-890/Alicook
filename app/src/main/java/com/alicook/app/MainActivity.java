
package com.alicook.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.res.Configuration;
import android.content.Intent;
import android.net.Uri;
import android.content.Context;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.webkit.ValueCallback;
import android.webkit.WebResourceRequest;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;

public class MainActivity extends Activity {
    WebView web;
    private final Handler timerHandler = new Handler(Looper.getMainLooper());
    private MediaPlayer alarm;
    private final Runnable ring = new Runnable() {
        @Override
        public void run() {
            startAlarm();
        }
    };
    private final Runnable autoStop = new Runnable() {
        @Override
        public void run() {
            stopAlarm();
        }
    };

    // Cooking timer signal: the phone's alarm sound (alarm volume, so it is heard even when media is muted)
    // plus vibration. It rings until the user turns it off, at most one minute.
    private void startAlarm() {
        stopAlarm();
        try {
            Uri uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (uri == null) uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            alarm = new MediaPlayer();
            alarm.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
            alarm.setDataSource(this, uri);
            alarm.setLooping(true);
            alarm.prepare();
            alarm.start();
        } catch (Exception e) {
            alarm = null;
        }
        try {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) {
                long[] pattern = {0, 600, 400, 600, 400, 600};
                if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createWaveform(pattern, 0));
                else v.vibrate(pattern, 0);
            }
        } catch (Exception ignored) {
        }
        timerHandler.postDelayed(autoStop, 60000);
        if (web != null) web.evaluateJavascript("window.onNativeTimerDone && window.onNativeTimerDone()", null);
    }

    private void stopAlarm() {
        timerHandler.removeCallbacks(autoStop);
        if (alarm != null) {
            try {
                alarm.stop();
            } catch (Exception ignored) {
            }
            alarm.release();
            alarm = null;
        }
        try {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) v.cancel();
        } catch (Exception ignored) {
        }
    }

    @Override
    protected void onDestroy() {
        timerHandler.removeCallbacks(ring);
        stopAlarm();
        super.onDestroy();
    }

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        setContentView(web);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    // Photo credits and licenses open in the user's browser, not inside the app.
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (ActivityNotFoundException ignored) {
                    }
                    return true;
                }
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                boolean dark = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                        == Configuration.UI_MODE_NIGHT_YES;
                view.evaluateJavascript("window.applyDark && window.applyDark(" + dark + ")", null);
            }
        });
        // Cooking mode asks to keep the screen on while it is open.
        web.addJavascriptInterface(new ScreenBridge(), "AliCook");
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(true);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setAllowFileAccessFromFileURLs(false);
        web.getSettings().setAllowUniversalAccessFromFileURLs(false);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        WebView.setWebContentsDebuggingEnabled(false);
        web.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        // Let the page close the open recipe, list or panel first; leave the app only from the main list.
        web.evaluateJavascript("(window.appBack && window.appBack()) ? 'yes' : 'no'", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String handled) {
                if (!"\"yes\"".equals(handled)) {
                    systemBack();
                }
            }
        });
    }

    private void systemBack() {
        super.onBackPressed();
    }

    private class ScreenBridge {
        @JavascriptInterface
        public void share(final String text) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Intent send = new Intent(Intent.ACTION_SEND);
                    send.setType("text/plain");
                    send.putExtra(Intent.EXTRA_TEXT, text);
                    try {
                        startActivity(Intent.createChooser(send, null));
                    } catch (ActivityNotFoundException ignored) {
                    }
                }
            });
        }

        @JavascriptInterface
        public void startTimer(final int seconds) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    timerHandler.removeCallbacks(ring);
                    stopAlarm();
                    timerHandler.postDelayed(ring, Math.max(1, seconds) * 1000L);
                }
            });
        }

        @JavascriptInterface
        public void cancelTimer() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    timerHandler.removeCallbacks(ring);
                    stopAlarm();
                }
            });
        }

        @JavascriptInterface
        public void keepScreenOn(final boolean on) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (on) {
                        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    } else {
                        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    }
                }
            });
        }
    }
}
