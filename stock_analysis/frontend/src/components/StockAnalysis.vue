<template>
  <div class="container">
    <div class="header">
      <h1>个股 AI 分析系统</h1>
    </div>

    <van-search
      v-model="stockCode"
      placeholder="请输入股票代码 (如 000001)"
      show-action
      @search="onSearch"
    >
      <template #action>
        <div @click="onSearch">分析</div>
      </template>
    </van-search>

    <van-tabs v-model:active="activeTab" @change="onTabChange" sticky>
      <van-tab title="AI 深度" name="deepseek"></van-tab>
      <van-tab title="盘中信号" name="intraday"></van-tab>
    </van-tabs>

    <div v-if="loading" class="loading-box">
      <van-loading type="spinner" color="#1989fa">分析中...</van-loading>
    </div>

    <div v-else-if="report" class="analysis-card">
      <div class="report-content" v-html="formattedReport"></div>
    </div>

    <div v-else-if="!loading && stockCode && searched" style="text-align: center; padding: 40px; color: #969799;">
      请输入代码并点击分析
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { showToast } from 'vant';
import axios from 'axios';
import { marked } from 'marked';

const stockCode = ref('');
const activeTab = ref('deepseek');
const loading = ref(false);
const report = ref('');
const searched = ref(false);
// 缓存分析结果，避免重复请求浪费 token
const cache = ref({});

const onSearch = async () => {
  if (!stockCode.value) {
    showToast('请输入股票代码');
    return;
  }
  
  let code = stockCode.value.trim();
  if (code.length < 6) {
    showToast('股票代码至少6位');
    return;
  }

  const type = activeTab.value;
  const cacheKey = `${code}_${type}`;

  // 如果缓存中已有结果，直接使用
  if (cache.value[cacheKey]) {
    report.value = cache.value[cacheKey];
    searched.value = true;
    return;
  }

  loading.value = true;
  searched.value = true;
  report.value = '';

    try {
    // 在 Docker 环境中，前端通过 Nginx 反向代理访问后端
    // 基础路径保持 /api 即可，Nginx 会自动转发
    const response = await axios.get('/api/analyze/' + code, {
      params: { type: type }
    });
    const result = response.data.report;
    report.value = result;
    // 存入缓存
    cache.value[cacheKey] = result;
  } catch (error) {
    console.error(error);
    showToast('分析失败: ' + (error.response?.data?.detail || error.message));
  } finally {
    loading.value = false;
  }
};

const onTabChange = () => {
  if (searched.value && stockCode.value) {
    onSearch();
  }
};

const formattedReport = computed(() => {
  if (!report.value) return '';
  return marked.parse(report.value);
});
</script>

<style scoped>
.container {
  padding-bottom: 50px;
  background-color: #f7f8fa;
  min-height: 100vh;
}
.header {
  background: #fff;
  padding: 15px;
  text-align: center;
  border-bottom: 1px solid #ebedf0;
  margin-bottom: 10px;
}
.header h1 {
  margin: 0;
  font-size: 18px;
  color: #323233;
}
.analysis-card {
  background: #fff;
  margin: 10px;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.report-content {
  font-size: 14px;
  line-height: 1.6;
  color: #323233;
  white-space: pre-wrap;
  word-break: break-all;
}
:deep(.report-content) h3 {
  font-size: 16px;
  margin-top: 15px;
  border-left: 4px solid #1989fa;
  padding-left: 8px;
}
:deep(.report-content) ul {
  padding-left: 20px;
}
.loading-box {
  text-align: center;
  padding: 40px;
}
</style>
