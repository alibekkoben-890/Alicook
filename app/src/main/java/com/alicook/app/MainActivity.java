
package com.alicook.app;

import android.app.Activity;
import android.app.AlarmManager;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.view.View;
import android.view.WindowInsets;
import android.widget.FrameLayout;
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
    /** The running activity, if any; the timer receiver uses it to ring inside the app. */
    static MainActivity current;
    WebView web;
    private FrameLayout root;
    private boolean resumed;
    private boolean timerPending;
    private boolean pendingDone;
    private boolean askedNotifications;
    private String timerText = "";
    private final Handler timerHandler = new Handler(Looper.getMainLooper());
    private MediaPlayer alarm;
    private final Runnable ring = new Runnable() {
        @Override
        public void run() {
            timerFired();
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

    private PendingIntent alarmIntent(String text) {
        Intent i = new Intent(this, TimerReceiver.class);
        if (text != null) i.putExtra("text", text);
        return PendingIntent.getBroadcast(this, 1, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    // The in-app Handler stops counting while the phone sleeps, so the timer is also given to the
    // system alarm clock: it wakes the phone and TimerReceiver shows a ringing notification.
    private void scheduleSystemAlarm(int seconds, String text) {
        AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        long at = System.currentTimeMillis() + Math.max(1, seconds) * 1000L;
        PendingIntent pi = alarmIntent(text);
        try {
            boolean exact = Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms();
            if (exact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
            else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
        } catch (Exception e) {
            try {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
            } catch (Exception ignored) {
            }
        }
    }

    private void cancelSystemAlarm() {
        try {
            AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
            if (am != null) am.cancel(alarmIntent(null));
        } catch (Exception ignored) {
        }
    }

    private void cancelTimerNotification() {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.cancel(TimerReceiver.NOTIFICATION_ID);
        } catch (Exception ignored) {
        }
    }

    // Android 13+ shows the timer notification only after the user allows notifications.
    private void askNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33 || askedNotifications) return;
        askedNotifications = true;
        try {
            if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
            }
        } catch (Exception ignored) {
        }
    }

    /** The timer ran out: called by the in-app Handler or by TimerReceiver, whichever comes first. */
    void timerFired() {
        if (!timerPending) return;
        timerPending = false;
        timerHandler.removeCallbacks(ring);
        cancelSystemAlarm();
        if (resumed) {
            startAlarm();
        } else {
            // The app is in the background: ring through a notification, tell the page when it is opened again.
            pendingDone = true;
            TimerReceiver.post(getApplicationContext(), timerText);
        }
    }

    boolean hasPendingTimer() {
        return timerPending;
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        cancelTimerNotification();
        if (pendingDone) {
            pendingDone = false;
            if (web != null) web.evaluateJavascript("window.onNativeTimerDone && window.onNativeTimerDone()", null);
        }
    }

    @Override
    protected void onPause() {
        resumed = false;
        super.onPause();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
    }

    private boolean isDark() {
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
    }

    // Android 15 draws the app under the status and navigation bars. The page is kept inside the
    // safe area by padding, and the bar icons are made dark on the light theme.
    private void styleSystemBars() {
        boolean dark = isDark();
        if (root != null) root.setBackgroundColor(dark ? 0xFF1E1E1E : 0xFFFFFFFF);
        if (Build.VERSION.SDK_INT >= 35) {
            try {
                int light = android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                android.view.WindowInsetsController c = getWindow().getInsetsController();
                if (c != null) c.setSystemBarsAppearance(dark ? 0 : light, light);
            } catch (Exception ignored) {
            }
        }
    }

    // Rotation, dark mode and similar changes no longer restart the activity (see configChanges in
    // the manifest), so the open recipe and a running timer survive them.
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        styleSystemBars();
        if (web != null) web.evaluateJavascript("window.applyDark && window.applyDark(" + isDark() + ")", null);
    }

    @Override
    protected void onDestroy() {
        // A running timer stays with the system alarm clock and will still ring as a notification.
        timerHandler.removeCallbacks(ring);
        stopAlarm();
        if (current == this) current = null;
        super.onDestroy();
    }

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        current = this;
        web = new WebView(this);
        root = new FrameLayout(this);
        root.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int l, t, r, b;
                if (Build.VERSION.SDK_INT >= 30) {
                    android.graphics.Insets s = insets.getInsets(WindowInsets.Type.systemBars()
                            | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                    l = s.left;
                    t = s.top;
                    r = s.right;
                    b = s.bottom;
                } else {
                    l = insets.getSystemWindowInsetLeft();
                    t = insets.getSystemWindowInsetTop();
                    r = insets.getSystemWindowInsetRight();
                    b = insets.getSystemWindowInsetBottom();
                }
                v.setPadding(l, t, r, b);
                return insets;
            }
        });
        styleSystemBars();
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
                view.evaluateJavascript("window.applyDark && window.applyDark(" + isDark() + ")", null);
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
            startTimerText(seconds, "");
        }

        /** Starts the cooking timer; text is shown in the notification if the app is in the background. */
        @JavascriptInterface
        public void startTimerText(final int seconds, final String text) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    timerHandler.removeCallbacks(ring);
                    stopAlarm();
                    cancelTimerNotification();
                    timerText = text == null ? "" : text;
                    timerPending = true;
                    pendingDone = false;
                    timerHandler.postDelayed(ring, Math.max(1, seconds) * 1000L);
                    scheduleSystemAlarm(seconds, timerText);
                    askNotificationPermission();
                }
            });
        }

        @JavascriptInterface
        public void cancelTimer() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    timerPending = false;
                    pendingDone = false;
                    timerHandler.removeCallbacks(ring);
                    cancelSystemAlarm();
                    cancelTimerNotification();
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

        /** HTTPS requests for Home Connect (Bosch/Siemens/Neff); only Home Connect hosts are allowed. */
        @JavascriptInterface
        public void httpRequest(final int id, final String method, final String url, final String headersJson, final String body) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    int status = 0;
                    String text;
                    java.net.HttpURLConnection c = null;
                    try {
                        java.net.URL u = new java.net.URL(url);
                        String host = u.getHost();
                        if (!"https".equals(u.getProtocol()) || !(host.equals("api.home-connect.com") || host.equals("simulator.home-connect.com"))) {
                            throw new SecurityException("host not allowed");
                        }
                        c = (java.net.HttpURLConnection) u.openConnection();
                        c.setConnectTimeout(15000);
                        c.setReadTimeout(20000);
                        c.setRequestMethod(method);
                        org.json.JSONObject h = new org.json.JSONObject(headersJson == null || headersJson.isEmpty() ? "{}" : headersJson);
                        java.util.Iterator<String> keys = h.keys();
                        while (keys.hasNext()) {
                            String k = keys.next();
                            c.setRequestProperty(k, h.getString(k));
                        }
                        if (body != null && !body.isEmpty()) {
                            c.setDoOutput(true);
                            java.io.OutputStream os = c.getOutputStream();
                            os.write(body.getBytes("UTF-8"));
                            os.close();
                        }
                        status = c.getResponseCode();
                        java.io.InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
                        StringBuilder sb = new StringBuilder();
                        if (in != null) {
                            java.io.BufferedReader br = new java.io.BufferedReader(new java.io.InputStreamReader(in, "UTF-8"));
                            String line;
                            while ((line = br.readLine()) != null) sb.append(line).append('\n');
                            br.close();
                        }
                        text = sb.toString();
                    } catch (Exception e) {
                        text = String.valueOf(e.getMessage());
                    } finally {
                        if (c != null) c.disconnect();
                    }
                    final String js = "window.onHttp && window.onHttp(" + id + "," + status + "," + org.json.JSONObject.quote(text) + ")";
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (web != null) web.evaluateJavascript(js, null);
                        }
                    });
                }
            }).start();
        }

        /** Opens the Home Connect sign-in page in the browser. */
        @JavascriptInterface
        public void openUrl(final String url) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Uri u = Uri.parse(url);
                    String host = u.getHost() == null ? "" : u.getHost();
                    if (!"https".equals(u.getScheme())
                            || !(host.equals("home-connect.com") || host.endsWith(".home-connect.com"))) return;
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, u));
                    } catch (ActivityNotFoundException ignored) {
                    }
                }
            });
        }
    }
}
